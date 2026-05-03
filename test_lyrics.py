import argparse
import ffmpeg
import main


def process(pl_dir: str, make_reversed: bool):
    audio_path = 'Apple Music/Vibes/231.m4a'
    srt_path = 'Apple Music/Vibes/231.srt'
    probed_audio = main.probe_audio(audio_path)
    print(probed_audio)
    final = ffmpeg.output(
        main.get_processed_stream_lyric_video(
            duration=probed_audio['duration'],
            title='UwU',
            srt_path=srt_path,
            footer2='6767',
            make_reversed=make_reversed,
        ),
        main.get_processed_stream_audio(
            audio_path=audio_path,
            make_reversed=make_reversed,
        ),
        'gnsjdg-test.mp4',
        t=probed_audio['duration'],
    )
    ffmpeg.run(final, overwrite_output=True)


if __name__ == '__main__':
    args = argparse.ArgumentParser()
    args.add_argument(
        'pl_dir', type=str,
        default='./test', nargs='?',
    )
    args.add_argument(
        '--reverse', dest='make_reversed', action='store_true',
    )
    process(**args.parse_args().__dict__)
