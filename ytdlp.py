# pyright: basic, reportAssignmentType=false
from concurrent.futures import ThreadPoolExecutor
import argparse
import yt_dlp
import uuid
import os


from util import gen_txt_from_pl_infos, make_mp4, open_vlc


def get_list(u, make_reversed: bool) -> list[dict]:
    dl_client = yt_dlp.YoutubeDL({  # pyright: ignore[reportArgumentType]
        'dump_single_json': True,
        'playlistreverse': make_reversed,
        'skip_download': True,
        'simulate': True,
        'extract_flat': True,
        'noplaylist': False,
        'no_warnings': True,
        'quiet': True,
    })
    extracted_info: dict = dl_client.extract_info(u)
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
    ranks = extracted_info.get('requested_entries', None)
    if ranks is not None:
        pass
    elif make_reversed:
        ranks = range(+pl_count+0, +0, -1)
    else:
        ranks = range(+1, +pl_count+1, +1)

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


def process_pl_info(pl_dir: str, pl_info, make_reversed: bool):
    audio_temp_path = os.path.realpath(f"{pl_dir}/temp-{uuid.uuid4()}")
    try:
        dl_client = yt_dlp.YoutubeDL({
            'overwrites': True,
            'format': 'bestaudio',
            'outtmpl': audio_temp_path,
            'no_warnings': True,
            'quiet': True,
        })
        ext_info = dl_client.extract_info(pl_info["url"])
    except yt_dlp.utils.DownloadError:
        return

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

    if os.path.isfile(audio_temp_path):
        os.remove(audio_temp_path)

    return merged_info


def gen_cct_from_pl_infos(pl_dir: str, pl_infos: list) -> str:
    '''
    Makes a '.concat' string to be used with FFmpeg's 'concat' filter.
    '''
    return '\n'.join(
        "file " + get_file_num_str(pl_info)
        for pl_info in pl_infos
    )


def process(pl_dir: str, pl_url: str, make_reversed: bool) -> None:
    m3u_path = os.path.realpath(f"{pl_dir}/.m3u8")
    txt_path = os.path.realpath(f"{pl_dir}/.txt")
    cct_path = os.path.realpath(f"{pl_dir}/.concat")
    mp4_path = os.path.realpath(f"{pl_dir}/.mp4")
    pl_infos = get_list(pl_url, make_reversed)
    clear_cache_dir(pl_dir)

    with open(m3u_path, 'w', encoding='utf-8') as o:
        o.write(gen_m3u_from_pl_infos(pl_dir, pl_infos))

    with open(cct_path, 'w', encoding='utf-8') as o:
        o.write(gen_cct_from_pl_infos(pl_dir, pl_infos))

    executor = ThreadPoolExecutor(max_workers=1)
    futures = [
        executor.submit(
            process_pl_info,
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

    if os.path.isfile(mp4_path):
        os.remove(mp4_path)

    make_mp4(cct_path, mp4_path)

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
        help="%(type)s (default: \"%(default)s\")",
    )
    args.add_argument(
        '--no-reverse', dest='make_reversed', action='store_false',
        help="Does not tape-reverse your music",
    )
    process(**args.parse_args().__dict__)
