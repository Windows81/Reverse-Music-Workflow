import math
import subprocess
import argparse
import shutil
import yt_dlp
import ffmpeg
import re
import os

FPS = 2


def get_list(u) -> list:
    with yt_dlp.YoutubeDL({
        'dump_single_json': True,
        'playlistreverse': True,
        'extract_flat': True,
        'no_warnings': True,
        'quiet': True,
    }) as y:
        info = y.extract_info(u)
        if not info:
            raise Exception()
        pl_count = info['playlist_count']
        for pl_info, req_i in zip(info['entries'], info['requested_entries']):
            pl_info['playlist_url'] = info['webpage_url']
            pl_info['playlist_count'] = pl_count
            pl_info['playlist_rank'] = req_i
        return info['entries']


def get_name(pl_info) -> str:
    return f"cache/{pl_info['playlist_rank']:05d}.mp4"


def clear_folder(pl_dir: str) -> None:
    cache = os.path.realpath(f"{pl_dir}/cache")
    shutil.rmtree(cache, ignore_errors=True)
    os.makedirs(cache)


def gen_m3u(pl: list) -> str:
    return '\n'.join(
        [
            f'#EXTM3U',
        ] + [
            f'#EXTINF:-1,{pl_info["title"]}\n{get_name(pl_info)}'
            for pl_info in pl
        ]
    )


def format_time(t: int) -> str:
    t = int(t)
    if t < 3600:
        return f"{t // 60:d}:{t % 60:02d}"
    return f"{t // 3600:d}:{t // 60 % 60:02d}:{t % 60:02d}"


def gen_txt(pl: list) -> str:
    res = [pl[0]['playlist_url']]
    duration = 0
    for pl_info in pl:
        res.append(f'{format_time(duration)} {
                   pl_info["id"]} - {pl_info["title"]}')
        duration = duration + pl_info["duration"]
    return '\n'.join(res)


def drawtext_ts(s: str) -> str:
    return f'%{{expr_int_format:({s})/60:d:2}}:%{{expr_int_format:mod(({s})/1,60):d:2}}'


def probe_audio(mediapath):
    '''
    https://github.com/James4Ever0/pyjom/blob/df0d336af61b0f6611c196882dd6b0dbd4e18bab/pyjom/audiotoolbox.py#L26
    '''
    audio = ffmpeg.input(mediapath).audio

    stdout, stderr = (
        audio.filter("volumedetect")
        .output("/dev/null", f="null")
        .run(capture_stdout=True, capture_stderr=True)
    )

    format_regex = {
        'mean_volume': (re.compile(
            r"\[Parsed_volumedetect.+\] mean_volume: ([\-0-9\.]+) dB"
        ), lambda m: float(m.group(1))),
        'max_volume': (re.compile(
            r"\[Parsed_volumedetect.+\] max_volume: ([\-0-9\.]+) dB"
        ), lambda m: float(m.group(1))),
        'duration': (re.compile(
            r"  Duration: (\d+):(\d{2}):(\d{2}).(\d{2})"
        ), lambda m: math.ceil(
            int(m.group(1))*3600 +
            int(m.group(2))*60 +
            int(m.group(3))*1 +
            int(m.group(4))/100
        )),
    }

    ret_dict = {}
    stderr_lines: list[str] = stderr.decode("utf-8").split("\n")
    for line in stderr_lines:
        for i, (r, l) in format_regex.items():
            match = r.match(line)
            if match == None:
                continue
            ret_dict[i] = l(match)

    return ret_dict


def get_processed_stream_audio(merged_info: dict, audio_path: str):
    audio = ffmpeg.input(
        audio_path,
    )

    # volume_adj = max(
    #     -merged_info['mean_volume'] - 12,
    #     0,
    # )

    # audio = ffmpeg.filter(
    #     audio,
    #     'volume',
    #     f'{volume_adj}dB',
    # )

    audio = ffmpeg.filter(
        audio,
        'areverse',
    )

    return audio


def get_processed_stream_video(merged_info: dict):
    video = ffmpeg.input(
        f'color=color=#111111:r={FPS}:size=hd720',
        format='lavfi'
    )

    duration = merged_info["duration"]
    title = merged_info["title"]
    if len(title) > 23:
        title = re.split('\\s*[\\[\\({]', title, 1)[0].rstrip(' -')

    video = ffmpeg.drawtext(
        video,
        text=title,
        fontcolor='white',
        fontfile='0.ttf',
        fontsize=43,
        x='(w-tw)/2',  # type: ignore
        y='h/2-37',  # type: ignore
    )

    video = ffmpeg.drawtext(
        video,
        text=merged_info["webpage_url"],
        fontcolor='white',
        fontfile='1.ttf',
        fontsize=23,
        x='(w-tw)/2',  # type: ignore
        y='h/2+7',  # type: ignore
    )

    video = ffmpeg.drawtext(
        video,
        text=f'%d / %d' % (
            merged_info["playlist_rank"],
            merged_info["playlist_count"]
        ),
        fontcolor='white',
        fontfile='1.ttf',
        fontsize=19,
        x='(w-tw)/2',  # type: ignore
        y='h/2+31',  # type: ignore
    )

    video = ffmpeg.drawtext(
        video,
        text=drawtext_ts(f'{duration}-t'),
        escape_text=False,
        fontcolor='white',
        fontfile='1.ttf',
        fontsize=17,
        x='(w-tw)/2',  # type: ignore
        y='h/2+53',  # type: ignore
    )

    return video


def process_pl_info(dl_client: yt_dlp.YoutubeDL, pl_dir: str, pl_info):
    try:
        ext_info = dl_client.extract_info(pl_info['url'])
    except yt_dlp.utils.DownloadError:
        return

    audio_temp_path = os.path.realpath(f"{pl_dir}/temp")
    probed_audio = probe_audio(audio_temp_path)
    merged_info = pl_info | ext_info | probed_audio

    result_path = os.path.realpath(f"{pl_dir}/{get_name(merged_info)}")
    final = ffmpeg.output(
        get_processed_stream_audio(merged_info, audio_temp_path),
        get_processed_stream_video(merged_info),
        result_path,
        ab='128k',
        t=merged_info['duration'],
    )
    ffmpeg.run(final, overwrite_output=True)

    print(f'{merged_info["playlist_rank"]:5d} [{
          merged_info["id"]}] {merged_info["title"]}')
    return merged_info


def make_cct(pl_dir: str, pl_infos: list):
    '''
    Make '.concat' file for use with FFmpeg's 'concat' filter.
    '''
    mp4_path = os.path.realpath(f"{pl_dir}/.mp4")
    cct_path = os.path.realpath(f"{pl_dir}/.concat")
    with open(cct_path, 'w', encoding='utf-8') as o:
        o.write('\n'.join(
            "file " + get_name(pl_info)
            for pl_info in pl_infos
        ))

    if os.path.isfile(mp4_path):
        os.remove(mp4_path)

    cct_in = ffmpeg.input(cct_path, format='concat', safe=0)
    cct_out = ffmpeg.output(cct_in, mp4_path, max_interleave_delta=0, c='copy')
    ffmpeg.run(cct_out)


def open_vlc(path: str):
    subprocess.Popen(
        ['vlc', path],
        creationflags=0x00000008,
        close_fds=True,
    )


def main(pl_dir: str, pl_url: str) -> None:
    m3u_path = os.path.realpath(f"{pl_dir}/.m3u8")
    txt_path = os.path.realpath(f"{pl_dir}/.txt")
    audio_temp_path = os.path.realpath(f"{pl_dir}/temp")
    pl_infos = get_list(pl_url)

    clear_folder(pl_dir)
    with open(m3u_path, 'w', encoding='utf-8') as o:
        o.write(gen_m3u(pl_infos))

    dl_client = yt_dlp.YoutubeDL({
        'overwrites': True,
        'format': 'bestaudio',
        'outtmpl': audio_temp_path,
        'quiet': True,
    })

    new_infos = []
    played = False
    for pl_info in pl_infos:
        new_info = process_pl_info(
            dl_client,
            pl_dir,
            pl_info,
        )
        if not new_info:
            continue

        new_infos.append(new_info)
        if not played:
            played = True
            open_vlc(m3u_path)

    with open(txt_path, 'w', encoding='utf-8') as o:
        o.write(gen_txt(new_infos))
    os.remove(audio_temp_path)
    make_cct(pl_dir, new_infos)
    del dl_client


if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument('pl_url', type=str)
    args.add_argument('pl_dir', type=str, default='./test', nargs='?')
    main(**args.parse_args().__dict__)
