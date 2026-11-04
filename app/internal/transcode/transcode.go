// Package transcode builds and runs the ffmpeg composition.
package transcode

import (
	"context"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"modernize43/assets"
	"modernize43/internal/source"
)

const (
	captureSeconds = 30
	logoMargin     = 32
	logoShare      = 0.16
	introWidth     = 1920
	introHeight    = 1080
)

var videoEncode = []string{
	"-c:v", "libx264", "-preset", "medium", "-crf", "20", "-profile:v", "high",
	"-pix_fmt", "yuv420p",
	"-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
}

var audioEncode = []string{"-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-ac", "2"}

var (
	logoOnce sync.Once
	logoPath string
	logoErr  error
)

func logoFile() (string, error) {
	logoOnce.Do(func() {
		path := filepath.Join(os.TempDir(), "modernize43-joyn.png")
		if err := os.WriteFile(path, assets.JoynPNG, 0o644); err != nil {
			logoErr = err
			return
		}
		logoPath = path
	})
	return logoPath, logoErr
}

// ForegroundWidth derives the 1080-high foreground width from the display ratio.
func ForegroundWidth(dar float64) int {
	width := int(dar*1080/2+0.5) * 2
	if width < 2 {
		width = 2
	}
	if width > 1920 {
		width = 1920
	}
	return width
}

func buildArgs(sourceURL, output string, info source.Info, seconds int, logo string, withSilence bool) ([]string, error) {
	foregroundWidth := ForegroundWidth(info.DAR)
	var steps []string
	if info.FieldOrder == "tt" || info.FieldOrder == "bb" ||
		info.FieldOrder == "tb" || info.FieldOrder == "bt" {
		steps = append(steps, "yadif=deint=all:mode=send_frame")
	}
	if info.Crop != nil {
		steps = append(steps, fmt.Sprintf("crop=%d:%d:%d:%d",
			info.Crop.W, info.Crop.H, info.Crop.X, info.Crop.Y))
	}
	steps = append(steps, "split=2[bgv][fgv]")
	graph := "[0:v]" + strings.Join(steps, ",")
	graph += ";[bgv]scale=iw*sar:ih:flags=lanczos,setsar=1," +
		"scale=1920:1080:force_original_aspect_ratio=increase:flags=lanczos," +
		"crop=1920:1080,boxblur=20:2,eq=brightness=-0.06:saturation=0.75[bg]"
	graph += fmt.Sprintf(";[fgv]scale=%d:1080:flags=lanczos,setsar=1,cas=strength=0.35[fg]", foregroundWidth)
	graph += ";[bg][fg]overlay=(W-w)/2:0,setsar=1," +
		"setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709[v]"

	inputs := []string{"-i", sourceURL}
	index := 1
	label := "[v]"
	if logo == "joyn" {
		path, err := logoFile()
		if err != nil {
			return nil, fmt.Errorf("Das Logo konnte nicht bereitgestellt werden.")
		}
		logoWidth := int(float64(foregroundWidth)*logoShare/2+0.5) * 2
		if logoWidth < 160 {
			logoWidth = 160
		}
		logoX := (1920-foregroundWidth)/2 + logoMargin
		graph += fmt.Sprintf(";[%d:v]scale=%d:-1[lg];[v][lg]overlay=%d:%d[vv]",
			index, logoWidth, logoX, logoMargin)
		inputs = append(inputs, "-i", path)
		index++
		label = "[vv]"
	}
	audioMap := "0:a:0?"
	if withSilence {
		inputs = append(inputs, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo")
		audioMap = fmt.Sprintf("%d:a:0", index)
	}
	args := []string{"-y", "-v", "error", "-nostdin", "-rw_timeout", "30000000"}
	args = append(args, inputs...)
	args = append(args, "-t", fmt.Sprintf("%d", seconds),
		"-filter_complex", graph, "-map", label, "-map", audioMap)
	args = append(args, videoEncode...)
	args = append(args, audioEncode...)
	args = append(args, "-movflags", "+faststart", output)
	return append([]string{"ffmpeg"}, args...), nil
}

func encodeIntroArgs(introURL, output, fps string, hasAudio bool) []string {
	inputs := []string{"-i", introURL}
	audioMap := "0:a:0?"
	extra := []string{}
	if !hasAudio {
		inputs = append(inputs, "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo")
		audioMap = "1:a:0"
		extra = append(extra, "-shortest")
	}
	graph := fmt.Sprintf("scale=%d:%d:force_original_aspect_ratio=decrease:flags=lanczos,"+
		"pad=%d:%d:(ow-iw)/2:(oh-ih)/2,setsar=1,fps=%s,"+
		"setparams=color_primaries=bt709:color_trc=bt709:colorspace=bt709",
		introWidth, introHeight, introWidth, introHeight, fps)
	args := []string{"ffmpeg", "-y", "-v", "error", "-nostdin"}
	args = append(args, inputs...)
	args = append(args, "-map", "0:v:0", "-map", audioMap, "-vf", graph)
	args = append(args, videoEncode...)
	args = append(args, audioEncode...)
	args = append(args, extra...)
	return append(args, "-movflags", "+faststart", output)
}

func concatArgs(introPath, contentPath, output string) ([]string, error) {
	listing := output + ".concat.txt"
	var builder strings.Builder
	for _, path := range []string{introPath, contentPath} {
		builder.WriteString("file '" + strings.ReplaceAll(path, "'", `'\''`) + "'\n")
	}
	if err := os.WriteFile(listing, []byte(builder.String()), 0o600); err != nil {
		return nil, err
	}
	return []string{"ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
		"-i", listing, "-c", "copy", "-movflags", "+faststart", output}, nil
}

func run(ctx context.Context, args []string) error {
	command := exec.CommandContext(ctx, args[0], args[1:]...)
	var stderr strings.Builder
	command.Stderr = &stderr
	if err := command.Run(); err != nil {
		if ctx.Err() == context.DeadlineExceeded {
			return fmt.Errorf("Die Transkodierung hat das Zeitlimit überschritten.")
		}
		if exit, ok := err.(*exec.ExitError); ok {
			if line := lastLine(string(exit.Stderr)); line != "" {
				return fmt.Errorf("%s", line)
			}
		}
		return fmt.Errorf("ffmpeg ist fehlgeschlagen.")
	}
	return nil
}

func lastLine(text string) string {
	lines := strings.Split(strings.TrimSpace(text), "\n")
	for i := len(lines) - 1; i >= 0; i-- {
		if line := strings.TrimSpace(lines[i]); line != "" {
			return line
		}
	}
	return ""
}

// Transcode produces the finished film at output.
func Transcode(ctx context.Context, sourceURL, output string, info source.Info,
	seconds int, logo, introURL string) error {
	if introURL == "" {
		args, err := buildArgs(sourceURL, output, info, seconds, logo, false)
		if err != nil {
			return err
		}
		return run(ctx, args)
	}
	contentPath := output + ".content.mp4"
	introPath := output + ".intro.mp4"
	defer os.Remove(contentPath)
	defer os.Remove(introPath)
	args, err := buildArgs(sourceURL, contentPath, info, seconds, logo, !info.HasAudio)
	if err != nil {
		return err
	}
	if err := run(ctx, args); err != nil {
		return err
	}
	hasAudio, err := source.ProbeHasAudio(introURL, 30*time.Second)
	if err != nil {
		return err
	}
	if err := run(ctx, encodeIntroArgs(introURL, introPath, info.FPS, hasAudio)); err != nil {
		return err
	}
	args, err = concatArgs(introPath, contentPath, output)
	if err != nil {
		return err
	}
	return run(ctx, args)
}
