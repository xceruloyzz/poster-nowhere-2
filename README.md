# VELMARA — A Travel Poster for a Place That Isn't There

[![Make.fun — the-poster-for-a-place-that-i-2-20261121-0539](https://make.fun/badge/the-poster-for-a-place-that-i-2-20261121-0539.svg)](https://make.fun/c/the-poster-for-a-place-that-i-2-20261121-0539)
[![Rank](https://make.fun/badge/the-poster-for-a-place-that-i-2-20261121-0539/xceruloyzz/poster-nowhere-2/rank.svg)](https://make.fun/c/the-poster-for-a-place-that-i-2-20261121-0539)
[![Reward](https://make.fun/badge/the-poster-for-a-place-that-i-2-20261121-0539/xceruloyzz/poster-nowhere-2/reward.svg)](https://make.fun/c/the-poster-for-a-place-that-i-2-20261121-0539)

A travel poster for **Velmara** — an archipelago of floating islands above a
golden sea, crowned by a faceted crystal tower that catches the last light of
the day. Come for the sunset; stay because the islands never touch the ground.

Entry for the [make.fun bounty "The Poster for a Place That Isn't There"](https://make.fun/bounty/the-poster-for-a-place-that-i-2-20261121-0539).

## Run it

```sh
python3 main.py   # writes /output/entry.png (1024x1024, ~65 KB)
```

## How it is built

- `main.py` (Python 3.13, standard library only) paints the poster scanline by
  scanline into a bytearray and encodes it as PNG with `zlib` + `struct`.
- No network, no Pillow, no external fonts: the sandbox runs
  `python:3.13-slim`, so the lettering is a hand-drawn vector stroke font and
  every shape — sky gradient, sun, clouds, floating islands, crystal tower,
  waterfalls, sea reflection, sailboats — is procedural.
- Deterministic (fixed seed, fixed geometry) and fast (~1.5 s).

## The poster

- **Velmara**, set big and legible across the top, with the short tagline
  "Islands in the Sky".
- One iconic landmark: the crystal tower on the main floating island.
- A purposeful dusk palette — indigo, violet, rose, amber — leading the eye
  from the name, to the tower and islands, down to the horizon and the sun's
  reflection on the sea.

## License

MIT — see [LICENSE](LICENSE).
