# Third-party notices

## unslop (CC BY 4.0)

The viewer's stylesheet passes follow the method of **unslop** by Damir Sokolovsky ([@heydamir](https://github.com/heydamir/unslop)), licensed under [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/). Source inspected: commit `a6f121eee5f29c2f74976b75456feae8b66afb3a`. Changes made here: the project's real DOM and stylesheet were the baseline. Any demo video rendered with the upstream `story.mjs` must keep the credit "unslop by @heydamir", which is part of that renderer's output.

## Container base images and toolchains

The worker Dockerfiles in `sandboxes/` start from externally supplied, digest-pinned Python, Node, GCC and Rust images. Those images, their operating systems and toolchains carry their own licenses; none is redistributed here. See [docs/THIRD-PARTY-NOTICES.md](docs/THIRD-PARTY-NOTICES.md).

## Viewer dependencies

The Python package has no runtime dependencies. The viewer is built with React (MIT), lucide-react (ISC), Vite and Vitest (MIT), TypeScript (Apache-2.0), jsdom and Testing Library (MIT); the exact versions are pinned in `viewer/package-lock.json`. Each keeps its own license. The stylesheet names the typeface Inter but ships no font files.
