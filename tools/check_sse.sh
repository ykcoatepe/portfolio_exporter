#!/bin/sh
# check_sse.sh — sample SSE latency checker using curl and awk
# Usage: check_sse.sh [--threshold SECONDS] [URL]

set -eu

threshold="3"
url="http://127.0.0.1:51127/stream"

print_usage() {
    cat <<'USAGE'
Usage: check_sse.sh [--threshold SECONDS] [URL]

Fetches up to 10 lines from an SSE endpoint using curl -N, timestamping each line
and computing line-to-line inter-arrival times. Reports PASS if the median
inter-arrival is below the provided threshold (default 3 seconds), otherwise
reports FAIL.
USAGE
}

while [ "$#" -gt 0 ]; do
    case "$1" in
        --threshold)
            if [ "$#" -lt 2 ]; then
                printf >&2 'Error: --threshold requires a value.\n'
                exit 1
            fi
            threshold="$2"
            shift 2
            ;;
        --help|-h)
            print_usage
            exit 0
            ;;
        --*)
            printf >&2 'Error: unknown option %s\n' "$1"
            print_usage >&2
            exit 1
            ;;
        *)
            url="$1"
            shift
            ;;
    esac
done

if [ -z "$threshold" ]; then
    printf >&2 'Error: threshold must be provided.\n'
    exit 1
fi

curl -s -N "$url" | awk -v limit=10 -v threshold="$threshold" '
BEGIN {
    prev = -1
    line_count = 0
}
{
    now = systime()
    line_count++

    if (line_count > 1) {
        delta = now - prev
        deltas[line_count - 1] = delta
        delta_note = sprintf(" | +%.3fs", delta)
    } else {
        delta_note = ""
    }

    print strftime("%Y-%m-%d %H:%M:%S", now) " | " $0 delta_note

    prev = now

    if (line_count >= limit) {
        exit
    }
}
END {
    sample_count = line_count - 1
    if (line_count == 0) {
        print "No data received." > "/dev/stderr"
        exit 1
    }
    if (sample_count <= 0) {
        print "Insufficient data to compute inter-arrival times." > "/dev/stderr"
        exit 1
    }

    for (i = 1; i <= sample_count; i++) {
        sorted[i] = deltas[i]
    }

    for (i = 1; i <= sample_count; i++) {
        for (j = i + 1; j <= sample_count; j++) {
            if (sorted[j] < sorted[i]) {
                tmp = sorted[i]
                sorted[i] = sorted[j]
                sorted[j] = tmp
            }
        }
    }

    mid = int((sample_count + 1) / 2)
    if (sample_count % 2 == 0) {
        median = (sorted[mid] + sorted[mid + 1]) / 2
    } else {
        median = sorted[mid]
    }

    printf "Median inter-arrival: %.3fs (threshold %.3fs) -> ", median, threshold
    if (median < threshold + 0) {
        print "PASS"
        exit 0
    }
    print "FAIL"
    exit 1
}
'
