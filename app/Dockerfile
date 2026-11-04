FROM golang:1.24-alpine AS build

WORKDIR /src
COPY go.mod ./
COPY . .
RUN CGO_ENABLED=0 go build -trimpath -ldflags "-s -w" -o /out/modernize43 .

FROM alpine:3.20

RUN apk add --no-cache ffmpeg
COPY --from=build /out/modernize43 /usr/local/bin/modernize43

WORKDIR /srv
EXPOSE 8080
ENTRYPOINT ["modernize43", "--host", "0.0.0.0", "--port", "8080"]
