// window-shot：给运行中的 Windows 程序窗口截图，保存为 PNG。
//
// 用法：window-shot <进程名或PID> <输出png路径>
//
// 设计取舍：
//   - 纯 stdlib + syscall，不依赖 golang.org/x/sys，也不依赖任何 CGO，离线即可构建。
//   - 抓窗口用 PrintWindow(PW_RENDERFULLCONTENT) 而非屏幕截屏：命令行调用时控制台
//     窗口常压在前台，屏幕截屏会把控制台一起抓进去；PrintWindow 不受遮挡影响。
//   - 必须先 SetProcessDPIAware()：本进程若不感知 DPI，GetWindowRect 拿到的是被系统
//     缩放过的逻辑坐标，与物理像素不一致会导致截图被裁切。
//   - 输出前裁掉 Win10/11 的“不可见调整边框”：GetWindowRect 比肉眼可见的窗口每边大
//     7~8px，PrintWindow 把那一圈画成纯黑，不裁就是截图四边的黑边。
package main

import (
	"fmt"
	"image"
	"image/png"
	"os"
	"strconv"
	"strings"
	"syscall"
	"time"
	"unsafe"
)

var (
	user32   = syscall.NewLazyDLL("user32.dll")
	gdi32    = syscall.NewLazyDLL("gdi32.dll")
	dwmapi   = syscall.NewLazyDLL("dwmapi.dll")
	kernel32 = syscall.NewLazyDLL("kernel32.dll")

	procEnumWindows        = user32.NewProc("EnumWindows")
	procGetWindowThreadPID = user32.NewProc("GetWindowThreadProcessId")
	procIsWindowVisible    = user32.NewProc("IsWindowVisible")
	procIsIconic           = user32.NewProc("IsIconic")
	procGetWindowRect      = user32.NewProc("GetWindowRect")
	procGetWindowTextW     = user32.NewProc("GetWindowTextW")
	procGetClassNameW      = user32.NewProc("GetClassNameW")
	procGetWindowLongPtrW  = user32.NewProc("GetWindowLongPtrW")
	procGetWindow          = user32.NewProc("GetWindow")
	procSetProcessDPIAware = user32.NewProc("SetProcessDPIAware")
	procShowWindow         = user32.NewProc("ShowWindow")
	procSetForegroundWin   = user32.NewProc("SetForegroundWindow")
	procBringWindowToTop   = user32.NewProc("BringWindowToTop")
	procGetDC              = user32.NewProc("GetDC")
	procReleaseDC          = user32.NewProc("ReleaseDC")
	procPrintWindow        = user32.NewProc("PrintWindow")

	procCreateCompatibleDC = gdi32.NewProc("CreateCompatibleDC")
	procCreateDIBSection   = gdi32.NewProc("CreateDIBSection")
	procSelectObject       = gdi32.NewProc("SelectObject")
	procBitBlt             = gdi32.NewProc("BitBlt")
	procDeleteDC           = gdi32.NewProc("DeleteDC")
	procDeleteObject       = gdi32.NewProc("DeleteObject")

	procDwmGetWindowAttribute = dwmapi.NewProc("DwmGetWindowAttribute")

	// 进程名 → PID 查找用（Toolhelp 快照）。
	procCreateToolhelp32Snapshot = kernel32.NewProc("CreateToolhelp32Snapshot")
	procProcess32FirstW          = kernel32.NewProc("Process32FirstW")
	procProcess32NextW           = kernel32.NewProc("Process32NextW")
	procCloseHandle              = kernel32.NewProc("CloseHandle")
)

const (
	// DWMWA_EXTENDED_FRAME_BOUNDS：窗口“肉眼可见”的边界（物理像素，屏幕坐标）。
	dwmwaExtendedFrameBounds = 9

	gwlStyle  = ^uintptr(15) // GWL_STYLE = -16
	wsCaption = 0x00C00000   // WS_CAPTION = WS_BORDER | WS_DLGFRAME

	swRestore = 9

	srcCopy    = 0x00CC0020
	captureBlt = 0x40000000
	dibRGB     = 0

	// PW_RENDERFULLCONTENT：让 DWM 合成窗口也能被 PrintWindow 正确渲染。
	pwRenderFullContent = 0x00000002

	th32csSnapProcess = 0x00000002
	maxPath           = 260
)

type rect struct{ L, T, R, B int32 }

type bitmapInfoHeader struct {
	Size          uint32
	Width         int32
	Height        int32 // 负值 = 自上而下扫描行，取像素时无需翻转
	Planes        uint16
	BitCount      uint16
	Compression   uint32
	SizeImage     uint32
	XPelsPerMeter int32
	YPelsPerMeter int32
	ClrUsed       uint32
	ClrImportant  uint32
}

type bitmapInfo struct {
	Header bitmapInfoHeader
	Colors [1]uint32 // BI_RGB 32bpp 用不到调色板，仅满足结构体尺寸要求
}

// processEntry32 对应 Win32 的 PROCESSENTRY32W。字段顺序和宽度必须与 ABI 一致，
// 否则 Process32FirstW 会写坏内存；DefaultHeapID 在 64 位下是 ULONG_PTR。
type processEntry32 struct {
	Size            uint32
	CntUsage        uint32
	ProcessID       uint32
	DefaultHeapID   uintptr
	ModuleID        uint32
	CntThreads      uint32
	ParentProcessID uint32
	PriClassBase    int32
	Flags           uint32
	ExeFile         [maxPath]uint16
}

type candidate struct {
	hwnd  uintptr
	title string
	class string
	rect  rect
	area  int32
}

func main() {
	if len(os.Args) < 3 {
		fmt.Fprintln(os.Stderr, "用法: window-shot <进程名或PID> <输出png路径>")
		os.Exit(2)
	}
	target := os.Args[1]
	outPath := os.Args[2]

	// 让本进程按物理像素工作，否则 Rect/屏幕坐标会被 DPI 虚拟化。
	procSetProcessDPIAware.Call()

	pids, err := resolvePIDs(target)
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(2)
	}
	if len(pids) == 0 {
		fmt.Fprintf(os.Stderr, "没有找到进程 %q（检查进程名拼写，或用 tasklist 看实际名字）\n", target)
		os.Exit(3)
	}

	// 同名进程可能有多个，取“有可见主窗口且面积最大”的那个。
	var best candidate
	var bestPID uint32
	for _, pid := range pids {
		c := findMainWindow(pid)
		if c.hwnd == 0 {
			continue
		}
		if c.area > best.area {
			best, bestPID = c, pid
		}
	}
	if best.hwnd == 0 {
		fmt.Fprintf(os.Stderr, "进程 %s (PID %v) 没有可见的主窗口。\n", target, pids)
		fmt.Fprintln(os.Stderr, "常见原因：窗口被最小化到托盘、或程序以“后台启动/收进托盘”方式启动。")
		fmt.Fprintln(os.Stderr, "处理：再启动一次该程序（多数程序会把已有窗口显示出来），或手动点托盘图标，然后重跑本工具。")
		os.Exit(3)
	}
	fmt.Printf("pid=%d hwnd=0x%X class=%q title=%q rect=(%d,%d)-(%d,%d) %dx%d\n",
		bestPID, best.hwnd, best.class, best.title,
		best.rect.L, best.rect.T, best.rect.R, best.rect.B,
		best.rect.R-best.rect.L, best.rect.B-best.rect.T)

	// 最小化先还原：PrintWindow 对已最小化的窗口拿不到内容。
	// 置前只为兜底路径（BitBlt 截屏）服务，失败也不致命。
	if iconic, _, _ := procIsIconic.Call(best.hwnd); iconic != 0 {
		procShowWindow.Call(best.hwnd, swRestore)
		time.Sleep(400 * time.Millisecond)
	}
	procBringWindowToTop.Call(best.hwnd)
	procSetForegroundWin.Call(best.hwnd)
	time.Sleep(200 * time.Millisecond)

	// 还原/置前后窗口位置可能变化，重新取一次。
	var r rect
	if ok, _, _ := procGetWindowRect.Call(best.hwnd, uintptr(unsafe.Pointer(&r))); ok == 0 {
		fmt.Fprintln(os.Stderr, "GetWindowRect 失败")
		os.Exit(4)
	}
	w, h := r.R-r.L, r.B-r.T
	if w <= 0 || h <= 0 {
		fmt.Fprintf(os.Stderr, "窗口尺寸异常: %dx%d\n", w, h)
		os.Exit(4)
	}

	img, err := captureWindow(best.hwnd, w, h, r.L, r.T)
	if err != nil {
		fmt.Fprintf(os.Stderr, "截图失败: %v\n", err)
		os.Exit(5)
	}

	// 按 DWM 可见边界裁掉不可见边框（PrintWindow 在这圈里画的是纯黑）。
	trimMax := 16 // DWM 拿不到时只能靠黑边探测，允许裁得深一些
	if vis, ok := visibleFrame(best.hwnd); ok {
		fmt.Printf("窗口矩形=(%d,%d)-(%d,%d)  可见框=(%d,%d)-(%d,%d)\n",
			r.L, r.T, r.R, r.B, vis.L, vis.T, vis.R, vis.B)
		img = crop(img, r, vis)
		trimMax = 4 // DWM 边界实测仍可能差 1~2 px，留一点余量收尾
	}
	img = trimBlackEdges(img, trimMax)

	b := img.Bounds()
	f, err := os.Create(outPath)
	if err != nil {
		fmt.Fprintf(os.Stderr, "创建输出文件失败: %v\n", err)
		os.Exit(5)
	}
	defer f.Close()
	if err := png.Encode(f, img); err != nil {
		fmt.Fprintf(os.Stderr, "写 PNG 失败: %v\n", err)
		os.Exit(5)
	}
	fmt.Printf("已保存: %s (%dx%d)\n", outPath, b.Dx(), b.Dy())
}

// resolvePIDs 把命令行参数解析成 PID 列表：纯数字当 PID，否则当进程名查快照。
func resolvePIDs(target string) ([]uint32, error) {
	if pid, err := strconv.ParseUint(target, 10, 32); err == nil {
		return []uint32{uint32(pid)}, nil
	}
	return findPIDsByName(target)
}

// findPIDsByName 用 Toolhelp 快照枚举进程，按 exe 名匹配（不区分大小写）。
// 不用 Get-Process 之类的外部命令，避免依赖 shell 与输出格式。
func findPIDsByName(name string) ([]uint32, error) {
	if !strings.HasSuffix(strings.ToLower(name), ".exe") {
		name += ".exe"
	}
	snap, _, errno := procCreateToolhelp32Snapshot.Call(th32csSnapProcess, 0)
	if snap == ^uintptr(0) {
		return nil, fmt.Errorf("CreateToolhelp32Snapshot 失败: %v", errno)
	}
	defer procCloseHandle.Call(snap)

	var pids []uint32
	var entry processEntry32
	entry.Size = uint32(unsafe.Sizeof(entry))
	ok, _, _ := procProcess32FirstW.Call(snap, uintptr(unsafe.Pointer(&entry)))
	for ok != 0 {
		if strings.EqualFold(syscall.UTF16ToString(entry.ExeFile[:]), name) {
			pids = append(pids, entry.ProcessID)
		}
		entry.Size = uint32(unsafe.Sizeof(entry))
		ok, _, _ = procProcess32NextW.Call(snap, uintptr(unsafe.Pointer(&entry)))
	}
	return pids, nil
}

// visibleFrame 取 DWM 认为的可见边界；失败时返回 ok=false，由调用方走兜底裁剪。
func visibleFrame(hwnd uintptr) (rect, bool) {
	var r rect
	hr, _, _ := procDwmGetWindowAttribute.Call(hwnd, dwmwaExtendedFrameBounds,
		uintptr(unsafe.Pointer(&r)), unsafe.Sizeof(r))
	if hr != 0 {
		fmt.Fprintf(os.Stderr, "提示：DwmGetWindowAttribute 失败 (0x%X)，改用黑边探测\n", hr)
		return rect{}, false
	}
	if r.R-r.L <= 0 || r.B-r.T <= 0 {
		return rect{}, false
	}
	return r, true
}

// crop 把整窗口图裁到可见框。屏幕坐标相减得到框在窗口内的偏移，再夹到图像边界内。
func crop(img *image.RGBA, win, vis rect) *image.RGBA {
	x0, y0 := int(vis.L-win.L), int(vis.T-win.T)
	x1, y1 := x0+int(vis.R-vis.L), y0+int(vis.B-vis.T)
	b := img.Bounds()
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
		return img
	}
	out := image.NewRGBA(image.Rect(0, 0, x1-x0, y1-y0))
	for y := y0; y < y1; y++ {
		copy(out.Pix[(y-y0)*out.Stride:], img.Pix[y*img.Stride+x0*4:(y*img.Stride+x1*4)])
	}
	return out
}

// trimBlackEdges 逐边裁掉“纯黑”的边缘，单边最多裁 max 像素。
// 与 DWM 可见框配合使用：DWM 的边界实测仍会差 1~2 px，这里收尾抹平。
//
// 判定用“采样”而非“整行/整列全黑”：标题栏是浅色且铺满窗口全宽，会破坏整列判定，
// 所以左右边只取高度的 25%~95% 采样，上下边取宽度的 5%~95% 采样；
// 只要有一个采样点不是纯黑就立刻停手，避免把深色内容误裁掉。
func trimBlackEdges(img *image.RGBA, max int) *image.RGBA {
	b := img.Bounds()
	w, h := b.Dx(), b.Dy()
	if w == 0 || h == 0 {
		return img
	}
	black := func(x, y int) bool {
		i := y*img.Stride + x*4
		return img.Pix[i] < 16 && img.Pix[i+1] < 16 && img.Pix[i+2] < 16
	}
	step := func(n int) int {
		if s := n / 16; s > 1 {
			return s
		}
		return 1
	}
	vertical := func(x int) bool { // 左右边：纵向采样
		for y := h / 4; y < h; y += step(h) {
			if !black(x, y) {
				return false
			}
		}
		return true
	}
	horizontal := func(y int) bool { // 上下边：横向采样
		for x := w / 16; x < w; x += step(w) {
			if !black(x, y) {
				return false
			}
		}
		return true
	}

	l := 0
	for l < max && vertical(l) {
		l++
	}
	rt := 0
	for rt < max && vertical(w-1-rt) {
		rt++
	}
	t := 0
	for t < max && horizontal(t) {
		t++
	}
	bt := 0
	for bt < max && horizontal(h-1-bt) {
		bt++
	}
	if l == 0 && t == 0 && rt == 0 && bt == 0 {
		return img
	}
	fmt.Printf("黑边收尾裁剪: 左=%d 上=%d 右=%d 下=%d\n", l, t, rt, bt)
	return crop(img, rect{0, 0, int32(w), int32(h)}, rect{int32(l), int32(t), int32(w - rt), int32(h - bt)})
}

// findMainWindow 枚举目标进程的顶层窗口，挑面积最大的“带标题栏且可见”的那个。
// 不按标题/类名硬编码匹配：标题随语言变化，类名属于实现细节，都不可靠。
func findMainWindow(pid uint32) candidate {
	var best candidate
	cb := syscall.NewCallback(func(hwnd, _ uintptr) uintptr {
		var p uint32
		procGetWindowThreadPID.Call(hwnd, uintptr(unsafe.Pointer(&p)))
		if p != pid {
			return 1
		}
		if vis, _, _ := procIsWindowVisible.Call(hwnd); vis == 0 {
			return 1
		}
		// 只要有 owner 就是对话框/弹出窗口，主窗口没有 owner。
		if owner, _, _ := procGetWindow.Call(hwnd, 4 /*GW_OWNER*/); owner != 0 {
			return 1
		}
		style, _, _ := procGetWindowLongPtrW.Call(hwnd, gwlStyle)
		if uint32(style)&wsCaption != wsCaption {
			return 1
		}
		var r rect
		if ok, _, _ := procGetWindowRect.Call(hwnd, uintptr(unsafe.Pointer(&r))); ok == 0 {
			return 1
		}
		area := (r.R - r.L) * (r.B - r.T)
		if area <= best.area {
			return 1
		}
		best = candidate{
			hwnd:  hwnd,
			title: utf16Field(hwnd, procGetWindowTextW),
			class: utf16Field(hwnd, procGetClassNameW),
			rect:  r,
			area:  area,
		}
		return 1
	})
	procEnumWindows.Call(cb, 0)
	return best
}

func utf16Field(hwnd uintptr, proc *syscall.LazyProc) string {
	buf := make([]uint16, 512)
	n, _, _ := proc.Call(hwnd, uintptr(unsafe.Pointer(&buf[0])), uintptr(len(buf)))
	if n == 0 {
		return ""
	}
	return syscall.UTF16ToString(buf[:n])
}

// captureWindow 优先用 PrintWindow 让窗口自绘到内存 DC —— 这条路不受其他窗口遮挡，
// 也不会因为我们自己的控制台恰好压在上面而抓到别人的画面。
// PrintWindow 偶有窗口不响应返回 0，此时退回屏幕 BitBlt（要求窗口已置前）。
func captureWindow(hwnd uintptr, w, h, x, y int32) (*image.RGBA, error) {
	memDC, _, bits, cleanup, err := newDibDC(w, h)
	if err != nil {
		return nil, err
	}
	defer cleanup()

	if ok, _, _ := procPrintWindow.Call(hwnd, memDC, pwRenderFullContent); ok == 0 {
		fmt.Fprintln(os.Stderr, "提示：PrintWindow 失败，退回屏幕 BitBlt")
		screenDC, _, _ := procGetDC.Call(0)
		if screenDC == 0 {
			return nil, fmt.Errorf("GetDC(0) 失败")
		}
		defer procReleaseDC.Call(0, screenDC)
		if ok, _, _ := procBitBlt.Call(memDC, 0, 0, uintptr(w), uintptr(h), screenDC,
			uintptr(x), uintptr(y), srcCopy|captureBlt); ok == 0 {
			return nil, fmt.Errorf("BitBlt 失败")
		}
	}
	return dibToRGBA(bits, w, h), nil
}

// newDibDC 建一个装得下 w×h 的 32bpp 自上而下 DIB 及其内存 DC，并把 DIB 选入 DC。
func newDibDC(w, h int32) (memDC, bitmap uintptr, bits unsafe.Pointer, cleanup func(), err error) {
	screenDC, _, _ := procGetDC.Call(0)
	if screenDC == 0 {
		return 0, 0, nil, nil, fmt.Errorf("GetDC(0) 失败")
	}
	defer procReleaseDC.Call(0, screenDC)

	memDC, _, _ = procCreateCompatibleDC.Call(screenDC)
	if memDC == 0 {
		return 0, 0, nil, nil, fmt.Errorf("CreateCompatibleDC 失败")
	}

	bmi := bitmapInfo{Header: bitmapInfoHeader{
		Size:        uint32(unsafe.Sizeof(bitmapInfoHeader{})),
		Width:       w,
		Height:      -h, // 负高度 = 自上而下，省去后续翻转
		Planes:      1,
		BitCount:    32,
		Compression: dibRGB,
	}}
	bitmap, _, _ = procCreateDIBSection.Call(memDC, uintptr(unsafe.Pointer(&bmi)), dibRGB,
		uintptr(unsafe.Pointer(&bits)), 0, 0)
	if bitmap == 0 || bits == nil {
		procDeleteDC.Call(memDC)
		return 0, 0, nil, nil, fmt.Errorf("CreateDIBSection 失败")
	}

	old, _, _ := procSelectObject.Call(memDC, bitmap)
	cleanup = func() {
		procSelectObject.Call(memDC, old)
		procDeleteObject.Call(bitmap)
		procDeleteDC.Call(memDC)
	}
	return memDC, bitmap, bits, cleanup, nil
}

// dibToRGBA 把 DIB 的 BGRA 像素转成 Go 的 RGBA。
func dibToRGBA(bits unsafe.Pointer, w, h int32) *image.RGBA {
	src := unsafe.Slice((*byte)(bits), int(w)*int(h)*4)
	img := image.NewRGBA(image.Rect(0, 0, int(w), int(h)))
	for i := 0; i < len(src); i += 4 {
		img.Pix[i] = src[i+2]
		img.Pix[i+1] = src[i+1]
		img.Pix[i+2] = src[i]
		img.Pix[i+3] = 0xFF
	}
	return img
}
