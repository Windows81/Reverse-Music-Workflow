# pyright: basic
from concurrent.futures import ThreadPoolExecutor
import yt_dlp.utils
import subprocess
import itertools
import tempfile
import argparse
import shutil
import yt_dlp
import ffmpeg
import math
import re
import os

FPS = 2


def get_list(u, make_reversed: bool) -> list[dict]:
    with yt_dlp.YoutubeDL({  # pyright: ignore[reportArgumentType]
        'dump_single_json': True,
        'playlistreverse': make_reversed,
        'skip_download': True,
        'simulate': True,
        'extract_flat': True,
        'noplaylist': False,
        'no_warnings': True,
        'quiet': True,
    }) as y:
        extracted_info = y.extract_info(u)
        if not extracted_info:
            raise Exception()

        # If the input URL is not a playlist, encapsulate the info.
        pl_count = extracted_info.get('playlist_count')
        if pl_count is None:
            extracted_info['url'] = extracted_info['playlist_url'] = extracted_info['webpage_url']
            extracted_info['playlist_count'] = extracted_info['playlist_rank'] = 1
            return [extracted_info]

        entries: list[dict] = extracted_info['entries']

        pl_count = len(entries)
        ranks = extracted_info.get(
            'requested_entries',
            (
                itertools.count(+pl_count, -1)
                if make_reversed else
                itertools.count(+1, +1)
            ),
        )

        for pl_info, req_i in zip(entries, ranks):
            pl_info['playlist_url'] = extracted_info['webpage_url']
            pl_info['playlist_count'] = pl_count
            pl_info['playlist_rank'] = req_i
        return entries


def get_track_name(pl_info) -> str:
    title = pl_info.get("title", None)
    if title:
        return title
    url = pl_info["url"]
    return url.rsplit('/')[-1]


def get_file_num_str(pl_info) -> str:
    return "cache/%05d.mp4" % pl_info['playlist_rank']


def clear_cache_dir(pl_dir: str) -> None:
    cache = os.path.realpath(f"{pl_dir}/cache")
    shutil.rmtree(cache, ignore_errors=True)
    os.makedirs(cache)


def gen_m3u_from_pl_infos(pl_dir: str, pl_infos: list) -> str:
    return '\n'.join([
        f'#EXTM3U',
        *(
            v
            for pl_info in pl_infos
            for v in (
                f'#EXTINF:-1,{get_track_name(pl_info)}',
                get_file_num_str(pl_info),
            )
        ),
    ])


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
        f'color=color=#111111:r={FPS}:size=1280x120',
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
            text='-',
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


def process_pl_info(dl_client: yt_dlp.YoutubeDL, pl_dir: str, pl_info, make_reversed: bool):
    try:
        ext_info = dl_client.extract_info(pl_info["url"])
    except yt_dlp.utils.DownloadError:
        return

    audio_temp_path = os.path.realpath(f"{pl_dir}/temp")
    probed_audio = probe_audio(audio_temp_path)
    merged_info = {
        'duration': math.ceil(probed_audio["duration"])
    } | pl_info | ext_info | probed_audio

    result_path = os.path.realpath(f"{pl_dir}/{get_file_num_str(merged_info)}")
    final = ffmpeg.output(
        get_processed_stream_audio(
            audio_path=audio_temp_path,
            make_reversed=make_reversed,
        ),
        get_processed_stream_video(
            duration=merged_info["duration"],
            title=merged_info["title"],
            footer1=merged_info["webpage_url"],
            footer2=f'%d / %d' % (
                merged_info["playlist_rank"],
                merged_info["playlist_count"]
            ),
            make_reversed=make_reversed,
        ),
        result_path,
        ab="192k",
        t=merged_info["duration"],
    )
    ffmpeg.run(final, overwrite_output=True, quiet=True)

    print(
        '%5d [%s] %s' % (
            merged_info["playlist_rank"], merged_info["id"], merged_info["title"],
        )
    )
    return merged_info


def gen_cct_from_pl_infos(pl_dir: str, pl_infos: list) -> str:
    '''
    Makes a '.concat' string to be used with FFmpeg's 'concat' filter.
    '''
    return '\n'.join(
        "file " + get_file_num_str(pl_info)
        for pl_info in pl_infos
    )


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


def process(pl_dir: str, pl_url: str, make_reversed: bool) -> None:
    m3u_path = os.path.realpath(f"{pl_dir}/.m3u8")
    txt_path = os.path.realpath(f"{pl_dir}/.txt")
    cct_path = os.path.realpath(f"{pl_dir}/.concat")
    mp4_path = os.path.realpath(f"{pl_dir}/.mp4")
    audio_temp_path = os.path.realpath(f"{pl_dir}/temp")
    pl_infos = get_list(pl_url, make_reversed)
    clear_cache_dir(pl_dir)

    with open(m3u_path, 'w', encoding='utf-8') as o:
        o.write(gen_m3u_from_pl_infos(pl_dir, pl_infos))

    with open(cct_path, 'w', encoding='utf-8') as o:
        o.write(gen_cct_from_pl_infos(pl_dir, pl_infos))

    dl_client = yt_dlp.YoutubeDL({
        'overwrites': True,
        'format': 'bestaudio',
        'outtmpl': audio_temp_path,
        'no_warnings': True,
        'quiet': True,
    })

    executor = ThreadPoolExecutor(max_workers=3)
    futures = [
        executor.submit(
            process_pl_info,
            dl_client,
            pl_dir,
            pl_info,
            make_reversed,
        )
        for pl_info in pl_infos
    ]

    new_infos = []
    played = False
    for f in futures:
        new_info = f.result()
        if not new_info:
            continue
        new_infos.append(new_info)

        if not played:
            played = True
            open_vlc(m3u_path)

    with open(txt_path, 'w', encoding='utf-8') as o:
        o.write(gen_txt_from_pl_infos(pl_dir, pl_infos=new_infos))

    if os.path.isfile(audio_temp_path):
        os.remove(audio_temp_path)

    if os.path.isfile(mp4_path):
        os.remove(mp4_path)

    make_mp4(cct_path, mp4_path)

    del dl_client
    del executor


if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument(
        'pl_url', type=str,
        help="Playlist URL to be processed by yt-dlp",
    )
    args.add_argument(
        'pl_dir', type=str,
        default='./test', nargs='?',
    )
    args.add_argument(
        '--reverse', dest='make_reversed', action='store_true',
    )
    process(**args.parse_args().__dict__)
