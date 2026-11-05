# LabProof third-party notices

## Scope and project licensing

This notice records **locally inspected manifests and license texts**, not a complete legal clearance or a newly selected license for LabProof. The project `pyproject.toml` declares no project license, and no project LICENSE file was found in the inspected project tree. The owner must decide project licensing; third-party licenses below do not license LabProof itself.

Project paths refer to the repository root. UI paths refer to the `viewer/` directory. Any redistribution of built UI assets must retain the applicable notices below.

## Python runtime, development and local workers

| Local manifest / source | Observed scope |
|---|---|
| `pyproject.toml` | Python >=3.12; runtime dependencies `[]`; build backend `setuptools>=68`; test extra `pytest>=8,<10` |
| `sandboxes/rust/Cargo.toml`, `Cargo.lock` | Worker package only, empty external dependency list; lock contains `labproof-worker` and no third-party crates |
| `sandboxes/python/Dockerfile` | Approved externally supplied digest-pinned Python image; copies fixed authored worker/authorization fixtures |
| `sandboxes/node/Dockerfile` | Approved externally supplied digest-pinned Node image; native runtime, not an npm dependency install |
| `sandboxes/c/Dockerfile` | Externally supplied pinned GCC image and fixed compiled worker |
| `sandboxes/rust/Dockerfile` | Externally supplied pinned Rust image and offline/locked worker build |
| `sandboxes/python/hypothesis_codec.py`, `src/labproof/adapters/hypothesis_codec.py` | Proposed/unaccepted codec source, not a declared installed Python dependency or accepted runtime capability |

No third-party Python runtime distribution is declared by the LabProof wheel metadata. Python itself, development environments, container base operating systems, compilers and toolchains have separate licenses and potentially many components; dependency-free Python metadata does not waive their obligations. This pass did not inspect complete approved image inventories or Python/build/test distribution license sets. Preserve and review their actual licenses when redistributing those components; no guessed image/license inventory is supplied here. Hypothesis source presence is not proof of acquisition, installation, execution or redistribution of a Hypothesis wheel.

## Optional packaged browser application

The Python package does not import these libraries. The browser viewer in `viewer/` uses its `package.json` / `package-lock.json` dependency graph. Locally present runtime packages and actual license files inspected:

| Package | Locally installed version | License file |
|---|---|---|
| React | 19.3.1 | `viewer/node_modules/react/LICENSE` — MIT |
| React DOM | 19.3.1 | `viewer/node_modules/react-dom/LICENSE` — MIT |
| Scheduler (React DOM dependency) | 0.28.0 | `viewer/node_modules/scheduler/LICENSE` — MIT |
| Lucide React | 0.468.0 | `viewer/node_modules/lucide-react/LICENSE` — ISC with Feather attribution |

These are observed local versions, not a claim about every old/future release bundle. The viewer manifest also declares build/test tools including TypeScript, Vite, Vitest, React plugin/types, Testing Library and jsdom; the lockfile is the exact dependency inventory. Build/test packages are not automatically Python runtime dependencies or shipped browser code. A release owner must inspect the actual emitted assets and anything else redistributed, retaining further applicable notices rather than treating this runtime excerpt as an exhaustive software bill of materials.

### MIT notice — React, React DOM and Scheduler

The locally inspected LICENSE files contain the same notice:

```text
MIT License

Copyright (c) Meta Platforms, Inc. and affiliates.

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

### ISC notice — Lucide React

```text
ISC License

Copyright (c) for portions of Lucide are held by Cole Bemis 2013-2022 as part of Feather (MIT). All other copyright (c) for Lucide are held by Lucide Contributors 2022.

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted, provided that the above
copyright notice and this permission notice appear in all copies.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES
WITH REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF
MERCHANTABILITY AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR
ANY SPECIAL, DIRECT, INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES
WHATSOEVER RESULTING FROM LOSS OF USE, DATA OR PROFITS, WHETHER IN AN
ACTION OF CONTRACT, NEGLIGENCE OR OTHER TORTIOUS ACTION, ARISING OUT OF
OR IN CONNECTION WITH THE USE OR PERFORMANCE OF THIS SOFTWARE.
```

No install, dependency refresh, download, image build, execution or licensing change was performed to compile these notices. Final archive contents and complete redistribution obligations remain release-owner review gates.
