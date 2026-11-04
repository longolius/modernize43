// Package jobs keeps jobs in memory and runs them one at a time.
package jobs

import (
	"context"
	"crypto/rand"
	"encoding/hex"
	"fmt"
	"os"
	"sync"
	"time"

	"modernize43/internal/source"
	"modernize43/internal/transcode"
)

// Job is one transcoding request.
type Job struct {
	ID      string
	URL     string
	Logo    string
	Seconds int
	Intro   string
	Created time.Time

	mu      sync.Mutex
	state   string
	message string
	dir     string
	result  string
}

func (j *Job) Snapshot() (string, string, string) {
	j.mu.Lock()
	defer j.mu.Unlock()
	return j.state, j.message, j.result
}

func (j *Job) setState(state, message string) {
	j.mu.Lock()
	j.state = state
	j.message = message
	j.mu.Unlock()
}

func (j *Job) setResult(path string) {
	j.mu.Lock()
	j.result = path
	j.state = "done"
	j.mu.Unlock()
}

// Public returns the status payload.
func (j *Job) Public() map[string]any {
	state, message, result := j.Snapshot()
	payload := map[string]any{"id": j.ID, "state": state}
	if message != "" {
		payload["message"] = message
	}
	if state == "done" && result != "" {
		payload["result_url"] = "/jobs/" + j.ID + "/result.mp4"
	}
	return payload
}

// Manager owns the job registry and the worker.
type Manager struct {
	allowPrivate bool
	timeout      time.Duration
	retention    time.Duration
	mu           sync.Mutex
	jobs         map[string]*Job
	queue        chan *Job
}

// NewManager starts the worker and the retention janitor.
func NewManager(allowPrivate bool, retentionMinutes int) *Manager {
	manager := &Manager{
		allowPrivate: allowPrivate,
		timeout:      180 * time.Second,
		retention:    time.Duration(retentionMinutes) * time.Minute,
		jobs:         map[string]*Job{},
		queue:        make(chan *Job, 64),
	}
	go manager.worker()
	go manager.cleanup()
	return manager
}

// Create registers a job and queues it.
func (m *Manager) Create(sourceURL, logo string, seconds int, intro string) *Job {
	buffer := make([]byte, 5)
	_, _ = rand.Read(buffer)
	job := &Job{
		ID:      hex.EncodeToString(buffer),
		URL:     sourceURL,
		Logo:    logo,
		Seconds: seconds,
		Intro:   intro,
		Created: time.Now(),
		state:   "queued",
	}
	m.mu.Lock()
	m.jobs[job.ID] = job
	m.mu.Unlock()
	m.queue <- job
	return job
}

// AllowPrivate reports whether private source hosts are permitted.
func (m *Manager) AllowPrivate() bool {
	return m.allowPrivate
}

// Get returns a job or nil.
func (m *Manager) Get(id string) *Job {
	m.mu.Lock()
	defer m.mu.Unlock()
	return m.jobs[id]
}

func (m *Manager) worker() {
	for job := range m.queue {
		job.setState("running", "")
		directory, err := os.MkdirTemp("", "modernize43-"+job.ID+"-")
		if err != nil {
			job.setState("error", "Es konnte kein Arbeitsverzeichnis angelegt werden.")
			continue
		}
		job.mu.Lock()
		job.dir = directory
		job.mu.Unlock()
		output := directory + "/result.mp4"
		ctx, cancel := context.WithTimeout(context.Background(), m.timeout)
		info, err := source.Probe(job.URL, 60*time.Second)
		if err == nil {
			limit := (16.0 / 9.0) / 1.01
			if info.DAR >= limit {
				err = fmt.Errorf("Das Seitenverhältnis (aspect ratio %.2f) ist nicht schmaler als 16:9.", info.DAR)
			}
		}
		if err == nil {
			introURL := ""
			if job.Intro == "joyn" {
				introURL = source.PresetIntro()
			}
			err = transcode.Transcode(ctx, job.URL, output, info, job.Seconds, job.Logo, introURL)
		}
		cancel()
		if err == nil {
			if stat, statErr := os.Stat(output); statErr != nil || stat.Size() == 0 {
				err = fmt.Errorf("Es wurde keine Ausgabedatei erzeugt.")
			}
		}
		if err != nil {
			message := err.Error()
			if len(message) > 2000 {
				message = message[:2000]
			}
			job.setState("error", message)
			continue
		}
		job.setResult(output)
	}
}

func (m *Manager) cleanup() {
	for {
		time.Sleep(time.Minute)
		cutoff := time.Now().Add(-m.retention)
		var expired []*Job
		m.mu.Lock()
		for id, job := range m.jobs {
			if job.Created.Before(cutoff) {
				expired = append(expired, job)
				delete(m.jobs, id)
			}
		}
		m.mu.Unlock()
		for _, job := range expired {
			job.mu.Lock()
			directory := job.dir
			job.mu.Unlock()
			if directory != "" {
				_ = os.RemoveAll(directory)
			}
		}
	}
}
