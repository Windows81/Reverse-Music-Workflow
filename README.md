# Vip's Music-Reversing Workflow

I have interesting musical tastes. For this reason, simply isntalling Spotify or using YouTube Music's website won't work for me. I use this tool to download playlists from the internet and get all the songs to play backwards.

The outputs 

Executables installed for `ffmpeg` and `vlc` are required. You will also need to perform `pip install -r requirements.txt`.

## Examples of use

To download a YouTube playlist and use FFmpeg to reverse the songs to `./"Dance Pop Bangers"`:
```
python3 main.py --reverse "https://music.youtube.com/playlist?list=RDCLAK5uy_nfs_t4FUu00E5ED6lveEBBX1VMYe1mFjk" "Dance Pop Bangers"
```

To download a SoundCloud album to `./"Plugin ParaDice"` and *not* reverse the songs:
```
python3 main.py "https://soundcloud.com/aaaroh-abo-shadi/sets/plugin-paradice-a-gambling-ad" "Plugin ParaDice"

## Resultant File Tree

This tool generates `mp4` videos for timekeeping purposes; the file-size increase is negligible as they are rendered at 2 fr/s.

Any newly-created directories will contain an `m3u8` playlist file and a combined `mp4` be made with the following tree structure:

```
.
│   .concat
│   .m3u8
│   .mp4
│   .txt
│
└───cache
        00001.mp4
        00002.mp4
        00003.mp4
        00004.mp4
        ...
```