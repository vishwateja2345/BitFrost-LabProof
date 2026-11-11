# Third-party notices

## unslop (CC BY 4.0)

The viewer's stylesheet passes follow the method of **unslop** by Damir Sokolovsky ([@heydamir](https://github.com/heydamir/unslop)), licensed under [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/). Source inspected: commit `a6f121eee5f29c2f74976b75456feae8b66afb3a`. Changes made here: the project's real DOM and stylesheet were the baseline. Any demo video rendered with the upstream `story.mjs` must keep the credit "unslop by @heydamir", which is part of that renderer's output.

## Container base images and toolchains

The worker Dockerfiles in `sandboxes/` start from externally supplied, digest-pinned Python, Node, GCC and Rust images. Those images, their operating systems and toolchains carry their own licenses; none is redistributed here. See [docs/THIRD-PARTY-NOTICES.md](docs/THIRD-PARTY-NOTICES.md).

## External services (not bundled)

`labproof brief --live` calls two services that you operate or hold an account with: a [Bifrost](https://github.com/maximhq/bifrost) gateway (`scripts/live-brief/run.sh` pulls the pinned `maximhq/bifrost` container image and an Ollama model you supply) and the [Tavily](https://tavily.com) search API. Nothing from either service, and no model weights, are redistributed in this repository. Their licenses and terms of service apply to your use. Search excerpts and model text written into a brief come from those services and from the public pages they quote; they keep their original rights and are labelled with their sources.

## Viewer dependencies

The Python package has no runtime dependencies. The viewer is built with React (MIT), lucide-react (ISC), Vite and Vitest (MIT), TypeScript (Apache-2.0), jsdom and Testing Library (MIT); the exact versions are pinned in `viewer/package-lock.json`. Each keeps its own license. The viewer ships [Instrument Serif](https://github.com/Instrument/instrument-serif) under the SIL Open Font License 1.1. The license is included in [viewer/public/fonts](viewer/public/fonts/InstrumentSerif-OFL.txt).
