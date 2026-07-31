# pyright: basic
from concurrent.futures import ThreadPoolExecutor
import argparse
import os.path
import ffmpeg

from util import expand_glob, get_processed_stream_audio, get_processed_stream_lyric_video, make_mp4, open_vlc, probe_audio


def get_output_path(index: int, make_reversed: bool, extension: str = 'mp4') -> str:
    base = f'{index:03d}'
    if make_reversed:
        return f'{base}.r.{extension}'
    else:
        return f'{base}.f.{extension}'


def gen_m3u(items: list[tuple[int, str]], make_reversed: bool) -> str:
    return '\n'.join([
        f'#EXTM3U',
        *(
            v
            for (index, filename) in items
            for v in (
                f'#EXTINF:-1,{index}',
                get_output_path(index, make_reversed),
            )
        ),
    ])


def gen_cct(items: list[tuple[int, str]], make_reversed: bool) -> str:
    return '\n'.join(
        f'file {os.path.basename(get_output_path(index, make_reversed))}'
        for (index, filename) in items
    )


def process_file(audio_path: str, out_dir: str, index: int, total: int, make_reversed: bool):
    in_path_base = audio_path[:audio_path.rfind('.')]
    srt_path = in_path_base + '.srt'
    output_path = os.path.join(
        out_dir,
        get_output_path(index, make_reversed),
    )

    audio_probe = probe_audio(audio_path)
    final = ffmpeg.output(
        get_processed_stream_lyric_video(
            duration=audio_probe['duration'],
            title=f'{audio_probe['id3_artist']} - {audio_probe['id3_title']}',
            srt_path=srt_path,
            footer2=f'{index} / {total}',
            make_reversed=make_reversed,
        ),
        get_processed_stream_audio(
            audio_path=audio_path,
            make_reversed=make_reversed,
        ),
        output_path,
        t=audio_probe['duration'],
    )
    ffmpeg.run(final, overwrite_output=True, quiet=True)
    return audio_probe, index


def process(pl_glob: str, out_dir: str, make_reversed: bool):
    m3u_path = os.path.realpath(f"{out_dir}/.m3u8")
    cct_path = os.path.realpath(f"{out_dir}/.concat")
    mp4_path = os.path.realpath(f"{out_dir}/.mp4")
    filenames = expand_glob(pl_glob, make_reversed)

    with open(m3u_path, 'w', encoding='utf-8') as o:
        o.write(gen_m3u(filenames, make_reversed))

    with open(cct_path, 'w', encoding='utf-8') as o:
        o.write(gen_cct(filenames, make_reversed))

    executor = ThreadPoolExecutor(max_workers=2)
    futures = [
        executor.submit(
            process_file,
            audio_path,
            out_dir,
            index,
            len(filenames),
            make_reversed,
        )
        for (index, audio_path) in filenames
    ]

    played = False
    for f in futures:
        result, index = f.result()
        print(f'{index:3d} {result['id3_artist']} - {result['id3_title']}')
        if not played:
            played = True
            open_vlc(m3u_path)

    make_mp4(cct_path, mp4_path)


if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument(
        'pl_glob', type=str,
        default='./Apple Music/Vibes/*.m4a',
        help="%(type)s (default: \"%(default)s\")",
    )
    args.add_argument(
        'out_dir', type=os.path.dirname,
        default='./Apple Music/Vibes/',
        help="%(type)s (default: \"%(default)s\")",
    )
    args.add_argument(
        '--no-reverse', dest='make_reversed', action='store_false',
        help="Does not tape-reverse your music",
    )
    process(**args.parse_args().__dict__)
