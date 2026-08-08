FROM golang:1.23-alpine AS builder

RUN apk add --no-cache gcc musl-dev

WORKDIR /app

COPY go.mod go.sum ./
RUN go mod download

COPY . .
RUN CGO_ENABLED=0 GOOS=linux go build -o /aggregator ./cmd/aggregator/

FROM gcr.io/distroless/static-debian12:nonroot

COPY --from=builder /aggregator /aggregator

ENTRYPOINT ["/aggregator"]
