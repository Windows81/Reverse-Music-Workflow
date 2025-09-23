# Vip's Music-Reversing Workflow

I have interesting musical tastes. For this reason, simply isntalling Spotify or using YouTube Music's website won't work for me. I use this tool to download playlists from the internet and get all the songs to play backwards.

Executables installed for `ffmpeg` and `vlc` are required. You will also need to perform `pip install -r requirements.txt`.

## Examples of use

To download a YouTube playlist and use FFmpeg to reverse the songs:
```
python3 main.py --reverse "https://music.youtube.com/playlist?list=RDCLAK5uy_nfs_t4FUu00E5ED6lveEBBX1VMYe1mFjk" "Dance Pop Bangers 2025-09-23"
```

To download a SoundCloud album and *not* reverse the songs:
```
python3 main.py "https://soundcloud.com/aaaroh-abo-shadi/sets/plugin-paradice-a-gambling-ad" "Plugin ParaDice"
```

