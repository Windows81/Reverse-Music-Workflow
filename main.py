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


def format_time(t: int):
    t = int(t)
    if t < 3600:
        return f"{t//60:d}:{t%60:02d}"
    return f"{t//3600:d}:{t//60%60:02d}:{t%60:02d}"


def gen_txt(pl: list) -> str:
    res = [pl[0]['playlist_url']]
    duration = 0
    for pl_info in pl:
        res.append(f'{format_time(duration)} {pl_info["id"]} - {pl_info["title"]}')
        duration = duration + pl_info["duration"]
    return '\n'.join(res)


def drawtext_ts(s: str) -> str:
    return f'%{{expr_int_format:({s})/60:d:2}}:%{{expr_int_format:mod(({s})/1,60):d:2}}'


def process_pl_info(dl_client: yt_dlp.YoutubeDL, pl_dir: str, pl_info):
    pl_info.update(dl_client.extract_info(pl_info['url']))
    audio_temp_path = os.path.realpath(f"{pl_dir}/temp")

    audio_probe = ffmpeg.probe(audio_temp_path)
    pl_info['duration'] = duration = \
        math.ceil(audio_probe['format']['duration'] / FPS) * FPS

    audio = ffmpeg.input(audio_temp_path).filter('areverse')
    video = ffmpeg.input(f'color=color=#111111:r={FPS}:size=hd720', format='lavfi')

    title = pl_info["title"]
    if len(title) > 23:
        title = re.split('\s*[\[\({]', title, 1)[0].rstrip(' -')

    video = ffmpeg.drawtext(
        video,
        text=title,
        fontcolor='white',
        fontfile='0.ttf',
        fontsize=43,
        x='(w-tw)/2',
        y='h/2-37',
    )

    video = ffmpeg.drawtext(
        video,
        text=pl_info["webpage_url"],
        fontcolor='white',
        fontfile='1.ttf',
        fontsize=23,
        x='(w-tw)/2',
        y='h/2+7',
    )

    video = ffmpeg.drawtext(
        video,
        text=f'{pl_info["playlist_rank"]} / {pl_info["playlist_count"]}',
        fontcolor='white',
        fontfile='1.ttf',
        fontsize=19,
        x='(w-tw)/2',
        y='h/2+31',
    )

    video = ffmpeg.drawtext(
        video,
        text=drawtext_ts(f'{duration}-t'),
        escape_text=False,
        fontcolor='white',
        fontfile='1.ttf',
        fontsize=17,
        x='(w-tw)/2',
        y='h/2+53',
    )

    result_path = os.path.realpath(f"{pl_dir}/{get_name(pl_info)}")
    final = ffmpeg.output(audio, video, result_path, ab='128k', t=duration)
    ffmpeg.run(final, overwrite_output=True, quiet=True)

    # probe = ffmpeg.probe(result_path)
    # duration = float(probe['format']['duration'])
    # pl_info['duration'] = duration

    print(f'{pl_info["playlist_rank"]:5d} [{pl_info["id"]}] {pl_info["title"]}')
    return result_path


def make_cct(pl_dir: str, pl_infos: list):
    mp4_path = os.path.realpath(f"{pl_dir}/.mp4")
    cct_path = os.path.realpath(f"{pl_dir}/.concat")
    with open(cct_path, 'w', encoding='utf-8') as o:
        o.write('\n'.join(
            "file " + repr(os.path.realpath(f"{pl_dir}/{get_name(pl_info)}"))
            for pl_info in pl_infos
        ))

    cct_in = ffmpeg.input(cct_path, format='concat', safe=0)
    cct_out = ffmpeg.output(cct_in, mp4_path, max_interleave_delta=0, c='copy')
    ffmpeg.run(cct_out)


def main(pl_dir: str, pl_url: str) -> None:
    m3u_path = os.path.realpath(f"{pl_dir}/.m3u8")
    txt_path = os.path.realpath(f"{pl_dir}/.txt")
    audio_temp_path = os.path.realpath(f"{pl_dir}/temp")
    pl_infos = get_list(pl_url)

    clear_folder(pl_dir)
    with open(m3u_path, 'w', encoding='utf-8') as o:
        o.write(gen_m3u(pl_infos))

    with yt_dlp.YoutubeDL({
        'overwrites': True,
        'format': 'bestaudio',
        'outtmpl': audio_temp_path,
        'quiet': True,
    }) as dl_client:
        for m3u_i, pl_info in enumerate(pl_infos):
            process_pl_info(dl_client, pl_dir, pl_info)
            if m3u_i != 0:
                continue
            subprocess.Popen(
                ['vlc', m3u_path],
                creationflags=0x00000008,
                close_fds=True,
            )

    with open(txt_path, 'w', encoding='utf-8') as o:
        o.write(gen_txt(pl_infos))
    os.remove(audio_temp_path)
    make_cct(pl_dir, pl_infos)


if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument('pl_url', type=str)
    args.add_argument('pl_dir', type=str, default='./test', nargs='?')
    main(**args.parse_args().__dict__)
