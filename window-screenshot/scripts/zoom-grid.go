// zoom-grid：把 PNG 的指定区域放大并叠加坐标网格，用来量出控件的像素位置。
//
// 用法：zoom-grid <输入png> <输出png> <x> <y> <宽> <高> <放大倍数>
//
// 用途：自绘界面（没有原生控件句柄）只能按坐标点，需要先在图里量出按钮位置。
// 网格线每 10 像素一条（浅红），每 50 像素一条（亮蓝），配合放大倍数即可读出坐标；
// 输出坐标 = 区域左上角 + 网格读数，无需精确到像素，能落在控件内即可。
package main

import (
	"fmt"
	"image"
	"image/color"
	"image/draw"
	"image/png"
	"os"
	"strconv"
)

func main() {
	if len(os.Args) < 8 {
		fmt.Fprintln(os.Stderr, "用法: zoom-grid <输入png> <输出png> <x> <y> <宽> <高> <放大倍数>")
		os.Exit(2)
	}
	num := func(i int) int {
		v, err := strconv.Atoi(os.Args[i])
		if err != nil {
			fmt.Fprintf(os.Stderr, "参数 %d 不是整数: %q\n", i, os.Args[i])
			os.Exit(2)
		}
		return v
	}
	out := os.Args[2]
	x, y, w, h, scale := num(3), num(4), num(5), num(6), num(7)
	if w <= 0 || h <= 0 || scale < 1 {
		fmt.Fprintln(os.Stderr, "宽/高必须为正，放大倍数至少 1")
		os.Exit(2)
	}

	f, err := os.Open(os.Args[1])
	if err != nil {
		fmt.Fprintf(os.Stderr, "打开失败: %v\n", err)
		os.Exit(1)
	}
	src, _, err := image.Decode(f)
	f.Close()
	if err != nil {
		fmt.Fprintf(os.Stderr, "解码失败: %v\n", err)
		os.Exit(1)
	}
	b := src.Bounds()

	// 先裁到图像范围内的交集，避免越界读出黑边。
	x0, y0 := x, y
	x1, y1 := x+w, y+h
	if x0 < b.Min.X {
		x0 = b.Min.X
	}
	if y0 < b.Min.Y {
		y0 = b.Min.Y
	}
	if x1 > b.Max.X {
		x1 = b.Max.X
	}
	if y1 > b.Max.Y {
		y1 = b.Max.Y
	}
	if x1 <= x0 || y1 <= y0 {
		fmt.Fprintln(os.Stderr, "区域不在图像范围内")
		os.Exit(1)
	}

	dst := image.NewRGBA(image.Rect(0, 0, (x1-x0)*scale, (y1-y0)*scale))
	// 最近邻放大：文字边缘会硬一些，但每个源像素的位置关系一目了然，便于量坐标。
	for sy := y0; sy < y1; sy++ {
		for sx := x0; sx < x1; sx++ {
			r, g, bl, a := src.At(sx, sy).RGBA()
			for dy := 0; dy < scale; dy++ {
				for dx := 0; dx < scale; dx++ {
					dst.Set((sx-x0)*scale+dx, (sy-y0)*scale+dy, color.RGBA{
						R: uint8(r >> 8), G: uint8(g >> 8), B: uint8(bl >> 8), A: uint8(a >> 8),
					})
				}
			}
		}
	}

	// 网格画在放大后的图上：源坐标每 10 px 一条浅线，每 50 px 一条亮线。
	thin := color.RGBA{R: 255, G: 170, B: 170, A: 255}
	bold := color.RGBA{R: 0, G: 120, B: 255, A: 255}
	for gx := ((x0 + 9) / 10) * 10; gx < x1; gx += 10 {
		c := thin
		if gx%50 == 0 {
			c = bold
		}
		px := (gx - x0) * scale
		for py := 0; py < dst.Bounds().Dy(); py++ {
			draw.Draw(dst, image.Rect(px, py, px+1, py+1), &image.Uniform{C: c}, image.Point{}, draw.Src)
		}
	}
	for gy := ((y0 + 9) / 10) * 10; gy < y1; gy += 10 {
		c := thin
		if gy%50 == 0 {
			c = bold
		}
		py := (gy - y0) * scale
		for px := 0; px < dst.Bounds().Dx(); px++ {
			draw.Draw(dst, image.Rect(px, py, px+1, py+1), &image.Uniform{C: c}, image.Point{}, draw.Src)
		}
	}

	g, err := os.Create(out)
	if err != nil {
		fmt.Fprintf(os.Stderr, "创建输出失败: %v\n", err)
		os.Exit(1)
	}
	defer g.Close()
	if err := png.Encode(g, dst); err != nil {
		fmt.Fprintf(os.Stderr, "写 PNG 失败: %v\n", err)
		os.Exit(1)
	}
	fmt.Printf("已保存 %s：源区域 (%d,%d)-(%d,%d)，放大 %d 倍；网格每 10px 浅红、每 50px 蓝\n",
		out, x0, y0, x1, y1, scale)
}
