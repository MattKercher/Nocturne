<p align="center"><img src="https://jeffser.com/images/nocturne/logo.svg">
<h1 align="center">Nocturne</h1>

<p align="center">Nocturne is a Navidrome / Jellyfin client that brings all your music together in one place, Nocturne not only connects to existing instances but it's capable of installing and managing its own Navidrome instance</p>

<p align="center"><a href='https://flathub.org/apps/com.jeffser.Nocturne'><img width='190' alt='Download on Flathub' src='https://flathub.org/api/badge?locale=en'/></a></p>

---

> [!IMPORTANT]
> Please be aware that [GNOME Code of Conduct](https://conduct.gnome.org) applies to Nocturne before interacting with this repository.

> [!WARNING]
> AI generated issues and PRs will be denied, repeated offence will result in a ban from the repository.

## Features

- Exploration by songs, artists, albums, radios and playlists
- Playlist management
- Compatibility with Jellyfin, OpenSubsonic and local files
- Audio equalizer and audio visualizer
- Mpris integration
- Integrated Navidrome instance management
- Automatic lyrics fetching
- Downloads and offline mode
- Cool interface

## Screenies

HomePage | Song Queue | Lyrics | Song List | Album Page
:------------------:|:-----------------:|:----------------:|:---------------------------:|:--------------------:
![screenie1](https://jeffser.com/images/nocturne/screenie1.png) | ![screenie2](https://jeffser.com/images/nocturne/screenie2.png) | ![screenie3](https://jeffser.com/images/nocturne/screenie3.png) | ![screenie4](https://jeffser.com/images/nocturne/screenie4.png) | ![screenie5](https://jeffser.com/images/nocturne/screenie5.png)

## Dependencies
The following dependencies are requirements of the project.
- `python3 >= 3.13`
- `gtk4`
- `libadwaita-1 >= 1.9`
- `glib-2.0 >= 2.84.0`
- `libsecret`
- `gstreamer`
- `blueprint-compiler >= 0.18.0`
- `python-requests >= 2.33.1`
- `python-colorthief >= 0.2.1`
- `python-syncedlyrics >= 1.0.1`
- `python-mpris-server >= 0.10.0`
- `python-tinytag >= 2.2.1`

## Install
### Linux (Flatpak)
Most Linux distributions come with Flatpak preinstalled, make sure your device has [the Flathub repo enabled](https://flathub.org/en/setup).
```sh
flatpak install flathub com.jeffser.Nocturne
```

### Arch Linux (AUR)
Nocturne is packaged unofficially in the AUR, to install it first make sure you have an AUR helper such as [yay](https://github.com/jguer/yay).
```sh
yay -S nocturne
```

## Build
### Linux (Flatpak)
Dependencies are automatically managed and built depending on host environment.
```sh
flatpak-builder build com.jeffser.Nocturne.yml --force-clean --install-deps-from=flathub
flatpak-builder --run build com.jeffser.Nocturne.yml nocturne
```

### macOS
#### 1. Install Dependencies with [Homebrew](https://brew.sh/)
```sh
brew install python@3.14 meson ninja pkgconf \
  glib gtk4 libadwaita pygobject3 gstreamer \
  gobject-introspection libsecret \
  desktop-file-utils
```

#### 2. Install Project & Packages
```sh
# 1. Install blueprint-compiler
git clone https://github.com/GNOME/blueprint-compiler
cd blueprint-compiler
meson build --prefix=/usr/local
sudo ninja install -C build
cd ..

# 2. Clone the project
git clone https://github.com/Jeffser/Nocturne/
cd Nocturne

# 3. Install python packages
python3 -m venv ./venv
source ./venv/bin/activate
pip install requests colorthief syncedlyrics tinytag mpris-server
```

#### 3. Build Project
```sh
meson setup build --prefix=$HOME/.local
ninja -C build
ninja install -C build
```

#### 4. Run Development Build
```sh
nocturne
```

## Special Thanks
### Translators

Language                | Contributors
:-----------------------|:-----------
Spanish                 | [Jeffry Samuel](https://github.com/jeffser)
Catalan                 | [Jordi Bultó](https://github.com/formajestically)
Basque                  | [Ibai Oihanguren Sala](https://ibaios.eus)
German                  | [Martin Prokoph](https://github.com/Motschen)
Russian                 | [Aleksandr Shamaraev](https://github.com/AlexanderShad)
Simplified Chinese      | [Saul Gman](https://github.com/Ja4e)
Turkish                 | [Muhammed Emin Akalan](https://github.com/muhammedeminakalan)
Traditional Chinese     | [Yuan Chiu](https://yuaner.tw)
Croatian                | [Milo Ivir](https://github.com/milotype)
Telugu                  | [Aryan Karamtoth](https://github.com/spaciouskarter78)
