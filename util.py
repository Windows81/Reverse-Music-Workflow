# pyright: basic
import subprocess
import tempfile
import ffmpeg
import glob
import math
import re
import os

FPS = 2


def expand_glob(pl_glob: str, make_reversed: bool) -> list[tuple[int, str]]:
    result = list(enumerate(glob.glob(os.path.abspath(pl_glob)), 1))
    if make_reversed:
        result.reverse()
    return result


def format_time(t: int) -> str:
    t = int(t)
    if t < 3600:
        return f"{t // 60:d}:{t % 60:02d}"
    return f"{t // 3600:d}:{t // 60 % 60:02d}:{t % 60:02d}"


def gen_txt_from_pl_infos(pl_dir: str, pl_infos: list) -> str:
    res = [pl_infos[0]['playlist_url']]
    duration = 0
    for pl_info in pl_infos:
        res.append(
            '%s %s - %s' % (
                format_time(duration),
                pl_info['webpage_url'],
                pl_info['title'],
            )
        )
        duration = duration + pl_info["duration"]
    return '\n'.join(res)


def drawtext_ts(s: str) -> str:
    return f'%{{expr_int_format:({s})/60:d:2}}:%{{expr_int_format:mod(({s})/1,60):d:2}}'


def probe_audio(mediapath):
    '''
    https://github.com/James4Ever0/pyjom/blob/df0d336af61b0f6611c196882dd6b0dbd4e18bab/pyjom/audiotoolbox.py#L26
    '''
    audio = ffmpeg.input(filename=mediapath, dn=None, vn=None).audio

    stdout, stderr = (
        audio.filter("volumedetect")
        .output("/dev/null", f="null")
        .run(quiet=True)
    )

    format_regex = {
        'id3_title': (re.compile(
            r"    title           : ([^\r]+)"
        ), lambda m: m.group(1)),
        'id3_artist': (re.compile(
            r"    artist          : ([^\r]+)"
        ), lambda m: m.group(1)),

        'mean_volume': (re.compile(
            r"\[Parsed_volumedetect.+\] mean_volume: ([\-0-9\.]+) dB"
        ), lambda m: float(m.group(1))),

        'max_volume': (re.compile(
            r"\[Parsed_volumedetect.+\] max_volume: ([\-0-9\.]+) dB"
        ), lambda m: float(m.group(1))),

        'duration': (re.compile(
            r"  Duration: (\d+):(\d{2}):(\d{2}).(\d{2})"
        ), lambda m: (
            int(m.group(1))*3600 +
            int(m.group(2))*60 +
            int(m.group(3))*1 +
            int(m.group(4))/100
        )),
    }

    ret_dict = {}
    items_left = len(format_regex)
    stderr_lines: list[str] = stderr.decode("utf-8").split("\n")
    for line in stderr_lines:
        if items_left == 0:
            break
        for i, (r, l) in format_regex.items():
            match = r.match(line)
            if match == None:
                continue
            if i in ret_dict:
                continue
            ret_dict[i] = l(match)
            items_left -= 1
            break

    return ret_dict


def get_processed_stream_audio(audio_path: str, make_reversed: bool):
    audio = ffmpeg.input(
        audio_path,
        dn=None,
        vn=None,
    )

    if make_reversed:
        audio = ffmpeg.filter(
            audio,
            'areverse',
        )

    return audio


def get_processed_stream_video(duration: float, title: str, footer1: str, footer2: str, make_reversed: bool):
    video = ffmpeg.input(
        f'color=color=#111111:r={FPS}:size=1280x720',
        format='lavfi'
    )

    if len(title) > 23:
        title = re.split('\\s*[\\[\\({]', title, maxsplit=1)[0].rstrip(' -')

    video = ffmpeg.drawtext(
        video,
        text=title,
        fontcolor='white',
        fontfile='0.ttf',
        fontsize=43,
        x='(w-tw)/2',  # pyright: ignore[reportArgumentType]
        y='h/2-37',  # pyright: ignore[reportArgumentType]
    )

    video = ffmpeg.drawtext(
        video,
        text=footer1,
        fontcolor='white',
        fontfile='1.ttf',
        fontsize=23,
        x='(w-tw)/2',  # pyright: ignore[reportArgumentType]
        y='h/2+7',  # pyright: ignore[reportArgumentType]
    )

    video = ffmpeg.drawtext(
        video,
        text=footer2,
        fontcolor='white',
        fontfile='1.ttf',
        fontsize=19,
        x='(w-tw)/2',  # pyright: ignore[reportArgumentType]
        y='h/2+31',  # pyright: ignore[reportArgumentType]
    )

    video = ffmpeg.drawtext(
        video,
        text=drawtext_ts(
            f'{duration}-t'
            if make_reversed else
            f't'
        ),
        escape_text=False,
        fontcolor='white',
        fontfile='1.ttf',
        fontsize=17,
        x='(w-tw)/2',  # pyright: ignore[reportArgumentType]
        y='h/2+53',  # pyright: ignore[reportArgumentType]
    )

    return video


def process_srt(t: list[str], duration: float, make_reversed: bool = True) -> list[str]:
    def get_time(v: str) -> float:
        if len(v) == 9:
            v = "00:" + v
        h = int(v[:-10])
        m = int(v[-9:-7])
        s = int(v[-6:-4])
        l = int(v[-3:])
        return 1e3 * (60 * (60 * h + m) + s) + l

    def invert_chunk(v: str, index: int, offset: float) -> str:
        t = v.split("\n", 2)
        t[0] = str(index)
        a = []
        for v in t[1].split(" --> "):
            r = max(1e3 * offset - get_time(v), 0)
            H = math.floor(r / 3600000)
            M = math.floor(r / 60000 % 60)
            S = math.floor(r / 1000 % 60)
            L = math.floor(r % 1000)
            a.append(f"{H:02d}:{M:02d}:{S:02d},{L:03d}")

        a.reverse()
        t[1] = " --> ".join(a)
        return "\n".join(t)

    def trim_chunk(v: str) -> str:
        t = v.split("\n", 2)
        t[2].replace('\n', ' ')
        return '\n'.join(t)

    c = 1
    chunks = list[str]()
    empty_flag = True
    for l in t:
        stripped_line = l.strip(" \t\ufeff\n\r")
        if empty_flag and stripped_line == str(c):
            chunks.append(f"{c}")
            c += 1
            continue

        empty_flag = stripped_line == ''
        if empty_flag:
            continue

        chunks[-1] += '\n' + stripped_line

    # This section is to ensure that no two subtitles overlap at the same time.
    for c in range(len(chunks)-1):
        start_time_start = chunks[c].find('\n') + 1
        start_time_end = chunks[c].find(' -')
        last_end_time_start = chunks[c-1].find(' --> ') + 5
        last_end_time_end = chunks[c-1].find('\n', last_end_time_start)

        # Since there was addition, failure would yield 4 instead of -1:
        if last_end_time_start <= 4:
            continue

        start_time_str = chunks[c][start_time_start:start_time_end]
        last_end_time_str = chunks[c-1][last_end_time_start:last_end_time_end]
        if get_time(last_end_time_str) > get_time(start_time_str):
            chunks[c-1] = ''.join([
                chunks[c-1][:last_end_time_start],
                start_time_str,
                chunks[c-1][last_end_time_end:],
            ])

    if not make_reversed:
        return [
            f"{trim_chunk(l)}\n\n"
            for i, l in enumerate(chunks, 1)
        ]

    return [
        f"{invert_chunk(trim_chunk(l), index=i, offset=duration)}\n\n"
        for i, l in enumerate(reversed(chunks), 1)
    ]


def get_processed_stream_lyric_video(duration: float, title: str, srt_path: str, footer2: str, make_reversed: bool):
    if os.path.exists(srt_path):
        temp_descip, temp_srt_path = tempfile.mkstemp('.srt')
        read_data = open(srt_path, encoding='utf-8').readlines()
        open(temp_srt_path, 'w', encoding='utf-8').writelines(
            process_srt(
                read_data,
                duration=duration,
                make_reversed=make_reversed,
            ),
        )
    else:
        temp_descip = temp_srt_path = None

    video = ffmpeg.input(
        f'color=color=#111111:r={FPS}:size=hd720',
        format='lavfi'
    )

    if len(title) > 23:
        title = re.split('\\s*[\\[\\({]', title, maxsplit=1)[0].rstrip(' -')

    video = ffmpeg.drawtext(
        video,
        text=title,
        fontcolor='white',
        fontfile='0.ttf',
        fontsize=43,
        x='(w-tw)/2',  # pyright: ignore[reportArgumentType]
        y='h/2-37',  # pyright: ignore[reportArgumentType]
    )

    if temp_srt_path is not None:
        video = ffmpeg.filter(
            video,
            filter_name='subtitles',
            filename=os.path.abspath(temp_srt_path),
            fontsdir='.',
            force_style='Fontname=Inconsolata Expanded Medium,Fontsize=11,Alignment=6,Outline=0,MarginV=144',
        )
    else:
        video = ffmpeg.drawtext(
            video,
            text='...',
            fontcolor='white',
            fontfile='1.ttf',
            fontsize=23,
            x='(w-tw)/2',  # pyright: ignore[reportArgumentType]
            y='h/2+7',  # pyright: ignore[reportArgumentType]
        )

    video = ffmpeg.drawtext(
        video,
        text=footer2,
        fontcolor='white',
        fontfile='1.ttf',
        fontsize=19,
        x='(w-tw)/2',  # pyright: ignore[reportArgumentType]
        y='h/2+31',  # pyright: ignore[reportArgumentType]
    )

    video = ffmpeg.drawtext(
        video,
        text=drawtext_ts(
            f'{duration}-t'
            if make_reversed else
            f't'
        ),
        escape_text=False,
        fontcolor='white',
        fontfile='1.ttf',
        fontsize=17,
        x='(w-tw)/2',  # pyright: ignore[reportArgumentType]
        y='h/2+53',  # pyright: ignore[reportArgumentType]
    )

    if temp_descip:
        os.close(temp_descip)
    return video


def open_vlc(path: str):
    subprocess.Popen(
        ['vlc', path],
        creationflags=0x00000008,
        close_fds=True,
    )


def make_mp4(cct_path: str, mp4_path: str) -> None:
    cct_in = ffmpeg.input(filename=cct_path, format='concat', safe=0)
    cct_out = ffmpeg.output(cct_in, mp4_path, max_interleave_delta=0, c='copy')
    ffmpeg.run(stream_spec=cct_out, quiet=True)
