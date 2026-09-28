---
name: window-screenshot
description: 给 Windows 桌面程序窗口截图并保存为 PNG 时使用，处理窗口被遮挡、最小化、只在托盘的情形，并自动去掉截图黑边。
allowed-tools: Bash, Read, Glob
---

# Windows 窗口截图

截运行中的程序窗口，输出与肉眼所见一致的 PNG：含标题栏与状态栏，无黑边，不受其他窗口遮挡影响。

## 用法

```
cd <本技能>/scripts
./window-shot.exe <进程名或PID> <输出png路径>
```

```
./window-shot.exe WinTray.exe "D:/Data/Desktop/主页.png"
./window-shot.exe 38816 out.png
```

输出尺寸 = 窗口可见区域的物理像素，可直接用于文档、商店页、发布说明。

## 步骤

1. **确认窗口可见**。`PowerShell: (Get-Process <名字>).MainWindowHandle`，返回 0 说明窗口没显示，直接截会报「没有可见的主窗口」。
2. **让窗口显示出来**（窗口不可见时才需要，别杀进程）
   - 只在托盘：**再启动一次该程序的 exe**，多数程序有单实例逻辑，会激活已有实例把窗口显示出来。
   - 最小化：不用管，工具会自动还原。
   - 仍不行：手动点托盘图标或任务栏图标。
3. **截图**：执行上面的命令。
4. **验证**：`./check-edges.exe <png>`，四边黑边须全为 0；再看图确认标题栏、底部状态栏等内容完整。
5. **交付**：把 PNG 放到用户指定位置，同时用图片预览确认内容无误。

## 关键约束

- 抓窗口用 **PrintWindow(PW_RENDERFULLCONTENT)**，不用屏幕截屏。从命令行执行时控制台窗口常压在前台，屏幕截屏会把控制台一起抓进去。
- 进程必须先 `SetProcessDPIAware()`。否则高缩放屏幕上 `GetWindowRect` 返回逻辑坐标，截图会被裁切。
- **黑边来自 Windows 的不可见调整边框**：Win10/11 的窗口矩形比可见窗口每边大 7~8px，PrintWindow 把这一圈画成纯黑。工具用 `DwmGetWindowAttribute(DWMWA_EXTENDED_FRAME_BOUNDS)` 取可见框裁切，再用采样探测黑边收尾（DWM 边界实测仍差 1~2px）。
- **不按窗口标题/类名匹配窗口**：标题随语言变化，类名是实现的内部细节。工具按「同 PID + 可见 + 无 owner（排除对话框）+ 有标题栏」筛选，取面积最大者。
- 一个程序有多个同名进程时，取「有可见窗口且面积最大」的那个；多窗口程序想截特定窗口，改用 PID 并确保目标窗口在最前。
- 截图会顺带把目标窗口还原并置前，属预期副作用。

## 文件

| 文件 | 作用 |
| --- | --- |
| `scripts/window-shot.exe` | 截图主工具 |
| `scripts/window-shot.go` | 主工具源码（纯 stdlib + syscall，无第三方依赖） |
| `scripts/check-edges.exe` / `.go` | 检查 PNG 四边黑边厚度并打印四角像素值，用于验证 |
| `scripts/build.sh` | 重新构建两个 exe（需要 Go） |

## 重建

```
bash scripts/build.sh
```

脚本先找 PATH 里的 `go`，找不到则回退到 `$USERPROFILE/sdk/go*/bin/go.exe`。两个工具都是单文件 main 包，用单文件构建（file-based build），不需要 go.mod。
