// check-edges：检查 PNG 四边是否存在纯黑边，并打印四角/边中点的像素值。
//
// 用法：go run check-edges.go <png路径>
//
// 用途：验证窗口截图是否残留 Win10/11 的“不可见调整边框”黑边。
// 正常情况下四边全黑行列数都应为 0。
package main

import (
	"fmt"
	"image"
	_ "image/png"
	"os"
)

func main() {
	if len(os.Args) < 2 {
		fmt.Fprintln(os.Stderr, "用法: check-edges <png路径>")
		os.Exit(2)
	}
	f, err := os.Open(os.Args[1])
	if err != nil {
		fmt.Fprintf(os.Stderr, "打开文件失败: %v\n", err)
		os.Exit(1)
	}
	defer f.Close()
	img, _, err := image.Decode(f)
	if err != nil {
		fmt.Fprintf(os.Stderr, "解码失败: %v\n", err)
		os.Exit(1)
	}
	b := img.Bounds()
	w, h := b.Dx(), b.Dy()

	isBlack := func(x, y int) bool {
		r, g, bl, _ := img.At(x, y).RGBA()
		return r>>8 < 16 && g>>8 < 16 && bl>>8 < 16
	}
	// 一条边整行/整列全黑才算黑边，避免把窗口内的深色内容误判成边。
	lineBlack := func(fixed int, horizontal bool) bool {
		n := h
		if horizontal {
			n = w
		}
		for i := 0; i < n; i++ {
			x, y := fixed, i
			if horizontal {
				x, y = i, fixed
			}
			if !isBlack(x, y) {
				return false
			}
		}
		return true
	}
	// 从某条边向内逐条判断，遇到第一条不是全黑的线就停。
	edge := func(from, step, limit int, horizontal bool) int {
		n := 0
		for i := 0; i < limit; i++ {
			if !lineBlack(from+i*step, horizontal) {
				break
			}
			n++
		}
		return n
	}
	left := edge(0, 1, w, false)
	rgt := edge(w-1, -1, w, false)
	top := edge(0, 1, h, true)
	btm := edge(h-1, -1, h, true)

	fmt.Printf("图像 %dx%d\n", w, h)
	fmt.Printf("黑边(全黑行列): 左=%d 右=%d 上=%d 下=%d\n", left, rgt, top, btm)
	if left == 0 && rgt == 0 && top == 0 && btm == 0 {
		fmt.Println("结论: 无黑边")
	} else {
		fmt.Println("结论: 仍有黑边，检查截图流程是否跳过了裁剪")
	}

	// 四角与边中点的像素值，便于判断是“纯黑填充”还是内容本身偏暗。
	for _, p := range []struct {
		name string
		x, y int
	}{
		{"左上角", 0, 0}, {"右上角", w - 1, 0}, {"左下角", 0, h - 1}, {"右下角", w - 1, h - 1},
		{"左边中点", 0, h / 2}, {"右边中点", w - 1, h / 2},
		{"顶部中点", w / 2, 0}, {"底部中点", w / 2, h - 1},
	} {
		r, g, bl, a := img.At(p.x, p.y).RGBA()
		fmt.Printf("%-10s (%4d,%4d) RGBA=(%3d,%3d,%3d,%3d)\n", p.name, p.x, p.y, r>>8, g>>8, bl>>8, a>>8)
	}
}
