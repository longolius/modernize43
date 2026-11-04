// Package web serves the public HTTP interface.
package web

import (
	"encoding/json"
	"fmt"
	"html"
	"net/http"
	"os"
	"strconv"
	"strings"

	"modernize43/internal/jobs"
	"modernize43/internal/source"
)

// Handler serves the form, the job pages and the result files.
type Handler struct {
	manager *jobs.Manager
}

// New returns the HTTP handler.
func New(manager *jobs.Manager) http.Handler {
	handler := &Handler{manager: manager}
	mux := http.NewServeMux()
	mux.HandleFunc("/healthz", handler.health)
	mux.HandleFunc("/jobs", handler.create)
	mux.HandleFunc("/jobs/", handler.byID)
	mux.HandleFunc("/", handler.index)
	return mux
}

func (h *Handler) health(w http.ResponseWriter, r *http.Request) {
	w.Header().Set("Content-Type", "text/plain; charset=utf-8")
	_, _ = w.Write([]byte("ok"))
}

func (h *Handler) index(w http.ResponseWriter, r *http.Request) {
	if r.URL.Path != "/" {
		http.NotFound(w, r)
		return
	}
	writeHTML(w, http.StatusOK, renderForm(formData{Source: "url", Logo: "none", Intro: "none", Seconds: 30}))
}

type formData struct {
	URL     string
	Source  string
	Logo    string
	Intro   string
	Seconds int
	Error   string
}

func selectBlock(name string, choices [][2]string, current string) string {
	var builder strings.Builder
	builder.WriteString(`<select name="` + name + `">`)
	for _, choice := range choices {
		selected := ""
		if choice[0] == current {
			selected = " selected"
		}
		builder.WriteString(fmt.Sprintf(`<option value="%s"%s>%s</option>`,
			html.EscapeString(choice[0]), selected, html.EscapeString(choice[1])))
	}
	builder.WriteString("</select>")
	return builder.String()
}

func renderForm(data formData) string {
	message := ""
	if data.Error != "" {
		message = `<div class="status error">` + html.EscapeString(data.Error) + `</div>`
	}
	return page("modernize43", fmt.Sprintf(`<h1>modernize43</h1>
<p class="lead">Film-URL einfügen. Die ersten Sekunden werden als 1920×1080 mit unscharfem Hintergrund ausgegeben.</p>
<form action="/jobs" method="post">
<input type="url" name="url" placeholder="https://…/film.mp4" value="%s">
%s%s%s
<input type="number" name="seconds" min="1" max="600" value="%d" title="Sekunden des Films">
<button type="submit">Modernisieren</button>
</form>%s`,
		html.EscapeString(data.URL),
		selectBlock("source", [][2]string{{"url", "Eigene URL"}, {"arabella_hq", "Arabella (768×576)"}}, data.Source),
		selectBlock("logo", [][2]string{{"none", "Kein Logo"}, {"joyn", "Joyn oben links"}}, data.Logo),
		selectBlock("intro", [][2]string{{"none", "Ohne Vorspann"}, {"joyn", "Joyn-Vorspann"}}, data.Intro),
		data.Seconds, message))
}

func (h *Handler) create(w http.ResponseWriter, r *http.Request) {
	if r.Method != http.MethodPost {
		http.NotFound(w, r)
		return
	}
	if err := r.ParseForm(); err != nil {
		writeHTML(w, http.StatusBadRequest, renderForm(formData{Source: "url", Logo: "none", Intro: "none", Seconds: 30, Error: "Das Formular konnte nicht gelesen werden."}))
		return
	}
	data := formData{
		URL:     r.FormValue("url"),
		Source:  valueOr(r.FormValue("source"), "url"),
		Logo:    valueOr(r.FormValue("logo"), "none"),
		Intro:   valueOr(r.FormValue("intro"), "none"),
		Seconds: 30,
	}
	if parsed, err := strconv.Atoi(strings.TrimSpace(r.FormValue("seconds"))); err == nil {
		data.Seconds = parsed
	} else if strings.TrimSpace(r.FormValue("seconds")) != "" {
		data.Seconds = 0
	}
	problem := ""
	switch {
	case data.Logo != "none" && data.Logo != "joyn":
		problem = "Unbekannte Logo-Option."
	case data.Intro != "none" && data.Intro != "joyn":
		problem = "Unbekannte Vorspann-Option."
	case data.Source != "url" && data.Source != "arabella_hq":
		problem = "Unbekannte Quelle."
	case data.Seconds < 1 || data.Seconds > 600:
		problem = "Die Dauer muss zwischen 1 und 600 Sekunden liegen."
	}
	if problem != "" {
		data.Error = problem
		if data.Seconds == 0 {
			data.Seconds = 30
		}
		writeHTML(w, http.StatusBadRequest, renderForm(data))
		return
	}
	candidate := data.URL
	if data.Source == "arabella_hq" {
		candidate = source.PresetArabellaHQ()
	}
	validated, err := source.ValidateURL(candidate, h.manager.AllowPrivate())
	if err != nil {
		data.Error = err.Error()
		writeHTML(w, http.StatusBadRequest, renderForm(data))
		return
	}
	job := h.manager.Create(validated, data.Logo, data.Seconds, data.Intro)
	w.Header().Set("Location", "/jobs/"+job.ID)
	w.WriteHeader(http.StatusSeeOther)
}

func (h *Handler) byID(w http.ResponseWriter, r *http.Request) {
	rest := strings.TrimPrefix(r.URL.Path, "/jobs/")
	parts := strings.Split(rest, "/")
	id := parts[0]
	if id == "" || !validID(id) {
		http.NotFound(w, r)
		return
	}
	suffix := ""
	if len(parts) > 1 {
		suffix = parts[1]
	}
	switch suffix {
	case "":
		h.jobPage(w, id)
	case "status":
		h.status(w, id)
	case "result.mp4":
		h.result(w, r, id)
	default:
		http.NotFound(w, r)
	}
}

func validID(id string) bool {
	for _, char := range id {
		if !(char >= 'a' && char <= 'z') && !(char >= 'A' && char <= 'Z') && !(char >= '0' && char <= '9') {
			return false
		}
	}
	return true
}

func (h *Handler) jobPage(w http.ResponseWriter, id string) {
	job := h.manager.Get(id)
	if job == nil {
		writeHTML(w, http.StatusNotFound, page("Nicht gefunden", "<h1>Job nicht gefunden</h1>"))
		return
	}
	state, message, _ := job.Snapshot()
	var body string
	switch state {
	case "done":
		body = fmt.Sprintf(`<h1>Fertig</h1>
<video controls playsinline src="/jobs/%s/result.mp4"></video>
<p><a class="download" href="/jobs/%s/result.mp4" download>MP4 herunterladen</a></p>
<p class="muted"><a href="/">Neuen Film modernisieren</a></p>`, id, id)
	case "error":
		body = fmt.Sprintf(`<h1>Fehler</h1><div class="status error">%s</div>
<p><a href="/">Zurück zum Formular</a></p>`, html.EscapeString(message))
	default:
		body = fmt.Sprintf(`<h1>Wird verarbeitet</h1>
<div class="status" id="status">Status: %s</div>
<p class="muted">Die Seite aktualisiert sich automatisch.</p>
<script>
const poll=()=>fetch('/jobs/%s/status').then(r=>r.json()).then(d=>{
if(d.state==='done'){location.reload();return;}
if(d.state==='error'){document.getElementById('status').textContent='Fehler: '+(d.message||'unbekannt');return;}
document.getElementById('status').textContent='Status: '+d.state;
setTimeout(poll,1000);}).catch(()=>setTimeout(poll,2000));
setTimeout(poll,500);
</script>`, state, id)
	}
	writeHTML(w, http.StatusOK, page("Job "+id, body))
}

func (h *Handler) status(w http.ResponseWriter, id string) {
	job := h.manager.Get(id)
	if job == nil {
		w.Header().Set("Content-Type", "application/json")
		w.WriteHeader(http.StatusNotFound)
		_ = json.NewEncoder(w).Encode(map[string]string{"error": "unbekannter Job"})
		return
	}
	w.Header().Set("Content-Type", "application/json")
	_ = json.NewEncoder(w).Encode(job.Public())
}

func (h *Handler) result(w http.ResponseWriter, r *http.Request, id string) {
	job := h.manager.Get(id)
	if job == nil {
		http.Error(w, "unbekannter Job", http.StatusNotFound)
		return
	}
	state, _, path := job.Snapshot()
	if state != "done" || path == "" {
		http.Error(w, "Ergebnis ist noch nicht verfügbar", http.StatusConflict)
		return
	}
	file, err := os.Open(path)
	if err != nil {
		http.Error(w, "Ergebnis ist nicht verfügbar", http.StatusConflict)
		return
	}
	defer file.Close()
	stat, err := file.Stat()
	if err != nil {
		http.Error(w, "Ergebnis ist nicht verfügbar", http.StatusConflict)
		return
	}
	w.Header().Set("Content-Type", "video/mp4")
	w.Header().Set("Content-Disposition", fmt.Sprintf(`attachment; filename="modernize43-%s.mp4"`, id))
	http.ServeContent(w, r, "modernize43-"+id+".mp4", stat.ModTime(), file)
}

func valueOr(value, fallback string) string {
	if strings.TrimSpace(value) == "" {
		return fallback
	}
	return value
}

func page(title, body string) string {
	return `<!doctype html><html lang="de"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>` + html.EscapeString(title) + `</title><style>` + style + `</style></head><body><main>` + body + `</main></body></html>`
}

func writeHTML(w http.ResponseWriter, status int, body string) {
	w.Header().Set("Content-Type", "text/html; charset=utf-8")
	w.WriteHeader(status)
	_, _ = w.Write([]byte(body))
}

const style = `
:root { color-scheme: dark; }
* { box-sizing: border-box; }
body { margin: 0; font-family: system-ui, sans-serif; background: #101215; color: #e8eaed; }
main { max-width: 960px; margin: 0 auto; padding: 32px 20px 64px; }
h1 { font-size: 1.5rem; margin: 0 0 6px; }
p.lead { color: #9aa0a6; margin: 0 0 24px; }
form { display: flex; gap: 8px; flex-wrap: wrap; }
input[type=url], input[type=number], select { padding: 12px 14px; border-radius: 8px;
  border: 1px solid #33383e; background: #1a1d21; color: inherit; font-size: 1rem; }
input[type=url] { flex: 1 1 420px; }
input[type=number] { width: 110px; }
button { padding: 12px 20px; border-radius: 8px; border: 0; background: #4c8dff;
  color: #06101f; font-weight: 600; font-size: 1rem; cursor: pointer; }
video { width: 100%; border-radius: 10px; background: #000; margin: 16px 0; }
a.download { display: inline-block; padding: 12px 20px; border-radius: 8px;
  background: #1f2429; color: #e8eaed; text-decoration: none; border: 1px solid #33383e; }
.status { padding: 14px 16px; border-radius: 8px; background: #1a1d21;
  border: 1px solid #33383e; margin: 18px 0; }
.error { border-color: #7a2b2b; background: #2a1717; color: #ffb4b4; }
.muted { color: #9aa0a6; font-size: .9rem; }
`
