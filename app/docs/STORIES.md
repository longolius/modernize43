# User stories

- S-01: As the user I paste a direct URL to a 4:3 film into the form, get a job page, and after the
  job finishes I can watch the 16:9 clip in the page and download the MP4. Normal path: the source
  is readable, narrower than 16:9 and has audio. Failure path: the job ends in the error state and
  the message says why.
- S-02: As the user I paste a malformed URL or a non-media URL and get a readable error instead of a
  job that silently produces nothing. The form keeps my input so I can correct it.
- S-03: As the user I can see whether my job is queued, running, done or failed, and the page updates
  without a manual reload.
- S-04: As the user the original audio survives the transcode and stays in sync for the 30 seconds
  that are kept.
- S-05: As the operator I do not want the service to fetch loopback, private or link-local addresses
  when a URL is submitted, because that would let any visitor probe the internal network.
