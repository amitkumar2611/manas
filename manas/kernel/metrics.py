"""In-kernel metrics: counters, gauges, histograms — Prometheus text format.

Zero dependencies by design (local-first): scrape /metrics with Prometheus or
read `manas metrics` on the CLI. Label sets are kept small and bounded.
"""
import threading
from collections import defaultdict

_lock = threading.Lock()
DEFAULT_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0)


class _Metric:
    def __init__(self, name: str, help_: str) -> None:
        self.name, self.help = name, help_


class Counter(_Metric):
    def __init__(self, name: str, help_: str) -> None:
        super().__init__(name, help_)
        self.values: dict[tuple, float] = defaultdict(float)

    def inc(self, amount: float = 1.0, **labels) -> None:
        with _lock:
            self.values[tuple(sorted(labels.items()))] += amount


class Gauge(_Metric):
    def __init__(self, name: str, help_: str) -> None:
        super().__init__(name, help_)
        self.values: dict[tuple, float] = {}

    def set(self, value: float, **labels) -> None:
        with _lock:
            self.values[tuple(sorted(labels.items()))] = value


class Histogram(_Metric):
    def __init__(self, name: str, help_: str,
                 buckets: tuple = DEFAULT_BUCKETS) -> None:
        super().__init__(name, help_)
        self.buckets = buckets
        self.counts: dict[tuple, list[int]] = {}
        self.sums: dict[tuple, float] = defaultdict(float)
        self.totals: dict[tuple, int] = defaultdict(int)

    def observe(self, value: float, **labels) -> None:
        key = tuple(sorted(labels.items()))
        with _lock:
            if key not in self.counts:
                self.counts[key] = [0] * (len(self.buckets) + 1)
            for i, b in enumerate(self.buckets):
                if value <= b:
                    self.counts[key][i] += 1
                    break
            else:
                self.counts[key][-1] += 1
            self.sums[key] += value
            self.totals[key] += 1


class Registry:
    def __init__(self) -> None:
        self._metrics: dict[str, _Metric] = {}

    def counter(self, name: str, help_: str = "") -> Counter:
        return self._metrics.setdefault(name, Counter(name, help_))  # type: ignore

    def gauge(self, name: str, help_: str = "") -> Gauge:
        return self._metrics.setdefault(name, Gauge(name, help_))  # type: ignore

    def histogram(self, name: str, help_: str = "") -> Histogram:
        return self._metrics.setdefault(name, Histogram(name, help_))  # type: ignore

    @staticmethod
    def _fmt_labels(key: tuple, extra: str = "") -> str:
        parts = [f'{k}="{v}"' for k, v in key]
        if extra:
            parts.append(extra)
        return "{" + ",".join(parts) + "}" if parts else ""

    def render(self) -> str:
        """Prometheus text exposition format."""
        out: list[str] = []
        for m in self._metrics.values():
            kind = {"Counter": "counter", "Gauge": "gauge",
                    "Histogram": "histogram"}[type(m).__name__]
            out += [f"# HELP {m.name} {m.help}", f"# TYPE {m.name} {kind}"]
            if isinstance(m, (Counter, Gauge)):
                for key, v in m.values.items():
                    out.append(f"{m.name}{self._fmt_labels(key)} {v}")
            else:
                for key in m.totals:
                    cum = 0
                    for i, b in enumerate(m.buckets):
                        cum += m.counts[key][i]
                        out.append(f"{m.name}_bucket"
                                   f"{self._fmt_labels(key, f'le=\"{b}\"')} {cum}")
                    cum += m.counts[key][-1]
                    out.append(f"{m.name}_bucket"
                               f"{self._fmt_labels(key, 'le=\"+Inf\"')} {cum}")
                    out.append(f"{m.name}_sum{self._fmt_labels(key)} "
                               f"{round(m.sums[key], 6)}")
                    out.append(f"{m.name}_count{self._fmt_labels(key)} "
                               f"{m.totals[key]}")
        return "\n".join(out) + "\n"


registry = Registry()

# -- core kernel metrics, instrumented across layers ------------------------
LLM_REQS = registry.counter("manas_llm_requests_total",
                            "LLM completions by provider and status")
LLM_LAT = registry.histogram("manas_llm_latency_seconds",
                             "LLM completion latency")
TOOL_RUNS = registry.counter("manas_tool_runs_total",
                             "Tool invocations by tool and status")
TOOL_LAT = registry.histogram("manas_tool_latency_seconds",
                              "Tool execution latency")
TASKS = registry.counter("manas_tasks_total",
                         "Orchestrated tasks by final status")
MEM_OPS = registry.counter("manas_memory_ops_total",
                           "Memory operations by op and tier")
