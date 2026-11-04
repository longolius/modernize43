// Package source validates source URLs and measures their geometry.
package source

import (
	"context"
	"encoding/json"
	"fmt"
	"net"
	"net/url"
	"os"
	"os/exec"
	"regexp"
	"strconv"
	"strings"
	"time"
)

var cropPattern = regexp.MustCompile(`crop=(\d+):(\d+):(\d+):(\d+)`)

// Crop describes the measured black-border crop.
type Crop struct {
	W int
	H int
	X int
	Y int
}

// Info is the measured source description.
type Info struct {
	Width    int
	Height   int
	SAR      string
	DAR      float64
	Crop       *Crop
	FieldOrder string
	FPS        string
	HasAudio bool
	Duration float64
}

// PresetIntro returns the configured Joyn intro URL.
func PresetIntro() string {
	if value := os.Getenv("MODERNIZE43_INTRO_URL"); value != "" {
		return value
	}
	return "https://hal.longolius.cc/joynintro.m4v"
}

// PresetArabellaHQ returns the configured high-quality Arabella preset URL.
func PresetArabellaHQ() string {
	if value := os.Getenv("MODERNIZE43_ARABELLA_HQ_URL"); value != "" {
		return value
	}
	return "https://hal.longolius.cc/arabella.m4v"
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

// DisplayRatio computes the display aspect ratio from pixel size, SAR and height.
func DisplayRatio(width, height int, sar string) float64 {
	num, den := 1, 1
	if parts := strings.SplitN(sar, ":", 2); len(parts) == 2 {
		if a, err := strconv.Atoi(parts[0]); err == nil {
			if b, err := strconv.Atoi(parts[1]); err == nil && a > 0 && b > 0 {
				num, den = a, b
			}
		}
	}
	return float64(width*num) / float64(height*den)
}

// ValidateURL accepts only absolute http(s) URLs and blocks private targets.
func ValidateURL(raw string, allowPrivate bool) (string, error) {
	value := strings.TrimSpace(raw)
	if value == "" {
		return "", fmt.Errorf("Bitte eine URL angeben.")
	}
	parsed, err := url.Parse(value)
	if err != nil {
		return "", fmt.Errorf("Die URL ist nicht gültig.")
	}
	if parsed.Scheme != "http" && parsed.Scheme != "https" {
		return "", fmt.Errorf("Nur http:// und https:// sind erlaubt.")
	}
	host := parsed.Hostname()
	if host == "" {
		return "", fmt.Errorf("Die URL enthält keinen Host.")
	}
	if !allowPrivate {
		addresses, err := net.LookupHost(host)
		if err != nil {
			return "", fmt.Errorf("Der Host %s konnte nicht aufgelöst werden.", host)
		}
		for _, address := range addresses {
			ip := net.ParseIP(address)
			if ip == nil {
				continue
			}
			if ip.IsPrivate() || ip.IsLoopback() || ip.IsLinkLocalUnicast() ||
				ip.IsLinkLocalMulticast() || ip.IsUnspecified() || ip.IsMulticast() {
				return "", fmt.Errorf("Private Netzwerkadressen sind nicht erlaubt.")
			}
		}
	}
	return value, nil
}

// Probe measures streams, display ratio and black borders.
func Probe(sourceURL string, timeout time.Duration) (Info, error) {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	command := exec.CommandContext(ctx, "ffprobe", "-v", "error", "-rw_timeout", "30000000",
		"-print_format", "json", "-show_streams", "-show_format", sourceURL)
	output, err := command.Output()
	if ctx.Err() == context.DeadlineExceeded {
		return Info{}, fmt.Errorf("Die Quelle antwortet nicht innerhalb von %d Sekunden.", int(timeout.Seconds()))
	}
	if err != nil {
		if exit, ok := err.(*exec.ExitError); ok {
			if line := lastLine(string(exit.Stderr)); line != "" {
				return Info{}, fmt.Errorf("%s", line)
			}
		}
		return Info{}, fmt.Errorf("Die Quelle konnte nicht gelesen werden.")
	}
	var payload struct {
		Streams []struct {
			CodecType         string `json:"codec_type"`
			Width             int    `json:"width"`
			Height            int    `json:"height"`
			SampleAspectRatio string `json:"sample_aspect_ratio"`
			AvgFrameRate      string `json:"avg_frame_rate"`
			RFrameRate        string `json:"r_frame_rate"`
			FieldOrder        string `json:"field_order"`
			Duration          string `json:"duration"`
		} `json:"streams"`
		Format struct {
			Duration string `json:"duration"`
		} `json:"format"`
	}
	if err := json.Unmarshal(output, &payload); err != nil {
		return Info{}, fmt.Errorf("ffprobe lieferte keine gültige Ausgabe.")
	}
	var video *struct {
		CodecType         string `json:"codec_type"`
		Width             int    `json:"width"`
		Height            int    `json:"height"`
		SampleAspectRatio string `json:"sample_aspect_ratio"`
		AvgFrameRate      string `json:"avg_frame_rate"`
		RFrameRate        string `json:"r_frame_rate"`
		FieldOrder        string `json:"field_order"`
		Duration          string `json:"duration"`
	}
	hasAudio := false
	for i := range payload.Streams {
		stream := &payload.Streams[i]
		if stream.CodecType == "audio" {
			hasAudio = true
		}
		if stream.CodecType == "video" && video == nil {
			video = stream
		}
	}
	if video == nil {
		return Info{}, fmt.Errorf("Die Quelle enthält keine Videospur.")
	}
	if video.Width <= 0 || video.Height <= 0 {
		return Info{}, fmt.Errorf("Die Bildabmessungen der Quelle sind unbekannt.")
	}
	sar := video.SampleAspectRatio
	if sar == "" {
		sar = "1:1"
	}
	fps := video.AvgFrameRate
	if fps == "" || fps == "0/0" {
		fps = video.RFrameRate
	}
	if fps == "" || fps == "0/0" {
		fps = "25/1"
	}
	crop := detectCrop(sourceURL, minDuration(timeout, 45*time.Second))
	crop = acceptableCrop(crop, video.Width, video.Height)
	croppedWidth, croppedHeight := video.Width, video.Height
	if crop != nil {
		croppedWidth, croppedHeight = crop.W, crop.H
	}
	duration, _ := strconv.ParseFloat(payload.Format.Duration, 64)
	if duration == 0 {
		duration, _ = strconv.ParseFloat(video.Duration, 64)
	}
	return Info{
		Width:    video.Width,
		Height:   video.Height,
		SAR:      sar,
		DAR:      DisplayRatio(croppedWidth, croppedHeight, sar),
		Crop:       crop,
		FieldOrder: video.FieldOrder,
		FPS:        fps,
		HasAudio: hasAudio,
		Duration: duration,
	}, nil
}

// ProbeHasAudio reports whether the URL carries an audio stream.
func ProbeHasAudio(sourceURL string, timeout time.Duration) (bool, error) {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	command := exec.CommandContext(ctx, "ffprobe", "-v", "error", "-rw_timeout", "30000000",
		"-print_format", "json", "-show_streams", sourceURL)
	output, err := command.Output()
	if ctx.Err() == context.DeadlineExceeded {
		return false, fmt.Errorf("Der Vorspann antwortet nicht innerhalb von %d Sekunden.", int(timeout.Seconds()))
	}
	if err != nil {
		if exit, ok := err.(*exec.ExitError); ok {
			if line := lastLine(string(exit.Stderr)); line != "" {
				return false, fmt.Errorf("%s", line)
			}
		}
		return false, fmt.Errorf("Der Vorspann konnte nicht gelesen werden.")
	}
	var payload struct {
		Streams []struct {
			CodecType string `json:"codec_type"`
		} `json:"streams"`
	}
	if err := json.Unmarshal(output, &payload); err != nil {
		return false, fmt.Errorf("ffprobe lieferte für den Vorspann keine gültige Ausgabe.")
	}
	for _, stream := range payload.Streams {
		if stream.CodecType == "audio" {
			return true, nil
		}
	}
	return false, nil
}

func detectCrop(sourceURL string, timeout time.Duration) *Crop {
	ctx, cancel := context.WithTimeout(context.Background(), timeout)
	defer cancel()
	command := exec.CommandContext(ctx, "ffmpeg", "-v", "info", "-nostdin",
		"-ss", "1", "-t", "4", "-i", sourceURL,
		"-vf", "cropdetect=24:2:0", "-f", "null", "-")
	var stderr strings.Builder
	command.Stderr = &stderr
	if err := command.Run(); err != nil {
		return nil
	}
	matches := cropPattern.FindAllStringSubmatch(stderr.String(), -1)
	if len(matches) == 0 {
		return nil
	}
	last := matches[len(matches)-1]
	values := make([]int, 4)
	for i := 0; i < 4; i++ {
		parsed, err := strconv.Atoi(last[i+1])
		if err != nil {
			return nil
		}
		values[i] = parsed
	}
	if values[0] <= 0 || values[1] <= 0 {
		return nil
	}
	return &Crop{W: values[0], H: values[1], X: values[2], Y: values[3]}
}

func acceptableCrop(crop *Crop, width, height int) *Crop {
	if crop == nil {
		return nil
	}
	if crop.W >= width && crop.H >= height {
		return nil
	}
	right := width - crop.W - crop.X
	bottom := height - crop.H - crop.Y
	limits := []struct{ margin, total int }{
		{crop.X, width}, {right, width}, {crop.Y, height}, {bottom, height},
	}
	for _, limit := range limits {
		if limit.margin < 0 || float64(limit.margin) > float64(limit.total)*0.2 {
			return nil
		}
	}
	if crop.W <= 0 || crop.H <= 0 {
		return nil
	}
	return crop
}

func minDuration(a, b time.Duration) time.Duration {
	if a < b {
		return a
	}
	return b
}
