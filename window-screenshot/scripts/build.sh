#!/usr/bin/env bash
# 构建本技能的两个小工具。
#
# Go 路径解析顺序：PATH 里的 go → 常见 SDK 安装位置（本机 Go 不在 Bash 的 PATH 里）。
# 产物落在脚本同目录，脚本可重复执行。
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$here"

go_exe="$(command -v go || true)"
if [ -z "$go_exe" ]; then
  # 兜底：用户自定义 SDK 目录下的 go1.*；取版本号最大的一个。
  go_exe="$(ls -d "$USERPROFILE"/sdk/go*/bin/go.exe "$HOME"/sdk/go*/bin/go.exe 2>/dev/null | sort -V | tail -1 || true)"
fi
if [ -z "$go_exe" ]; then
  echo "找不到 go，可执行文件，请先安装 Go 或把 go 加入 PATH" >&2
  exit 1
fi

# 每个工具都是单文件、独立 main 包，用 -s -w 去掉符号表压小体积。
# 不用 go.mod：两个文件都是 package main，同目录下会被当成一个包而 main 重名冲突，
# 单文件构建（file-based build）才是正确姿势，纯 stdlib 也不需要任何依赖解析。
build() {
  local src="$1" out="$2"
  echo "构建 $out"
  "$go_exe" build -ldflags "-s -w" -o "$out" "$src"
}

build window-shot.go window-shot.exe
build check-edges.go check-edges.exe
echo "完成：$here"
