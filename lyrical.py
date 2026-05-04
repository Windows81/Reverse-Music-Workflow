# pyright: basic
from concurrent.futures import ThreadPoolExecutor
import threading
import argparse
import os.path
import ffmpeg
import glob
import main


def expand_glob(pl_glob: str, make_reversed: bool) -> list[tuple[int, str]]:
    result = list(enumerate(glob.glob(os.path.abspath(pl_glob)), 1))
    if make_reversed:
        result.reverse()
    return result


def get_output_path(out_dir: str, index: int, make_reversed: bool) -> str:
    out_path_base = os.path.realpath(f'{out_dir}/{index:03d}')
    extension = 'ts'
    if make_reversed:
        return f'{out_path_base}.r.{extension}'
    else:
        return f'{out_path_base}.f.{extension}'


def gen_m3u(items: list[tuple[int, str]], out_dir: str, make_reversed: bool) -> str:
    return '\n'.join([
        f'#EXTM3U',
        *(
            v
            for (index, filename) in items
            for v in (
                f'#EXTINF:-1,{index}',
                get_output_path(out_dir, index, make_reversed),
            )
        ),
    ])


def gen_cct(items: list[tuple[int, str]], out_dir: str, make_reversed: bool) -> str:
    return '\n'.join(
        f'file {os.path.basename(get_output_path(out_dir, index, make_reversed))}'
        for (index, filename) in items
    )


def process_file(audio_path: str, out_dir: str, index: int, total: int, make_reversed: bool):
    in_path_base = audio_path[:audio_path.rfind('.')]
    srt_path = in_path_base + '.srt'
    output_path = get_output_path(out_dir, index, make_reversed)

    audio_probe = main.probe_audio(audio_path)
    final = ffmpeg.output(
        main.get_processed_stream_lyric_video(
            duration=audio_probe['duration'],
            title=f'{audio_probe['id3_artist']} - {audio_probe['id3_title']}',
            srt_path=srt_path,
            footer2=f'{index} / {total}',
            make_reversed=make_reversed,
        ),
        main.get_processed_stream_audio(
            audio_path=audio_path,
            make_reversed=make_reversed,
        ),
        output_path,
        t=audio_probe['duration'],
    )
    ffmpeg.run(final, overwrite_output=True, quiet=True)
    return audio_probe


def process(pl_glob: str, out_dir: str, make_reversed: bool):
    filenames = expand_glob(pl_glob, make_reversed)

    m3u_path = os.path.realpath(f"{out_dir}/.m3u8")
    with open(m3u_path, 'w', encoding='utf-8') as o:
        o.write(gen_m3u(filenames, out_dir, make_reversed))

    cct_path = os.path.realpath(f"{out_dir}/.concat")
    with open(cct_path, 'w', encoding='utf-8') as o:
        o.write(gen_cct(filenames, out_dir, make_reversed))

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
        result = f.result()
        print(f'{result['id3_artist']} - {result['id3_title']}')
        if not played:
            played = True
            main.open_vlc(m3u_path)


if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument(
        'pl_glob', type=str,
        default='./Apple Music/Vibes/*.m4a', nargs='?',
    )
    args.add_argument(
        'out_dir', type=os.path.dirname,
        default='./Apple Music/Vibes/', nargs='?',
    )
    args.add_argument(
        '--no-reverse', dest='make_reversed', action='store_false',
    )
    process(**args.parse_args().__dict__)
