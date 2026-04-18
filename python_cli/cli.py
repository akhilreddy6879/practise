# python_cli/cli.py
import typer
import yaml
from gha_client import GitHubActionsClient
from datetime import datetime

app = typer.Typer()

def load_config(path: str = "../services.yml"):
    with open(path) as f:
        return yaml.safe_load(f)["services"]

@app.command()
def list_services():
    """List services defined in services.yml."""
    services = load_config()
    for name, svc in services.items():
        typer.echo(f"{name}: {svc['owner']}/{svc['repo']} ({svc['workflow']})")

@app.command()
def trigger(service: str, ref: str | None = None):
    """Trigger a workflow for the given service."""
    services = load_config()
    if service not in services:
        typer.echo(f"Unknown service: {service}")
        raise typer.Exit(code=1)

    svc = services[service]
    client = GitHubActionsClient()

    data = {
        "ref": ref or svc.get("branch", "main"),
        "inputs": {},
    }
    path = f"/repos/{svc['owner']}/{svc['repo']}/actions/workflows/{svc['workflow']}/dispatches"
    client._request("POST", path, json=data)
    typer.echo(f"Triggered {service} on {data['ref']}")

@app.command()
@app.command()
def last_runs(service: str, limit: int = 5):
    """Show last workflow runs and conclusions."""
    services = load_config()
    if service not in services:
        typer.echo(f"Unknown service: {service}")
        raise typer.Exit(code=1)

    svc = services[service]
    client = GitHubActionsClient()
    path = f"/repos/{svc['owner']}/{svc['repo']}/actions/workflows/{svc['workflow']}/runs"
    data = client._request("GET", path, params={"per_page": limit})
    runs = data.get("workflow_runs", [])

    if not runs:
        typer.echo("No runs found")
        return

    for r in runs:
        typer.echo(
            f"{r['id']} - status={r['status']} "
            f"conclusion={r['conclusion']} "
            f"created_at={r['created_at']}"
        )

@app.command()
def metrics(service: str, limit: int = 20):
    """Show success rate, avg duration, last failure for a service."""
    services = load_config()
    if service not in services:
        typer.echo(f"Unknown service: {service}")
        typer.echo("Available services:")
        for name in services:
            typer.echo(f"  - {name}")
        raise typer.Exit(code=1)

    svc = services[service]
    client = GitHubActionsClient()

    path = f"/repos/{svc['owner']}/{svc['repo']}/actions/workflows/{svc['workflow']}/runs"
    data = client._request("GET", path, params={"per_page": limit})
    runs = data.get("workflow_runs", [])

    if not runs:
        typer.echo("No runs found")
        return

    total = len(runs)
    successes = [r for r in runs if r["conclusion"] == "success"]
    failures = [r for r in runs if r["conclusion"] == "failure"]
    success_rate = len(successes) / total * 100

    durations = []
    for r in runs:
        start = r.get("run_started_at") or r.get("created_at")
        end = r.get("updated_at")
        if start and end:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
            durations.append((end_dt - start_dt).total_seconds())

    avg_duration = sum(durations) / len(durations) if durations else 0

    last_failure_reason = None
    if failures:
        last_fail = failures[0]
        jobs_path = f"/repos/{svc['owner']}/{svc['repo']}/actions/runs/{last_fail['id']}/jobs"
        jobs_data = client._request("GET", jobs_path)
        failing_jobs = [
            j for j in jobs_data.get("jobs", [])
            if j.get("conclusion") == "failure"
        ]
        if failing_jobs:
            last_failure_reason = f"Job '{failing_jobs[0]['name']}' failed"

    typer.echo(f"Service: {service}")
    typer.echo(f"Runs analyzed: {total}")
    typer.echo(f"Success rate: {success_rate:.1f}%")
    typer.echo(f"Avg duration: {avg_duration:.1f}s")
    if last_failure_reason:
        typer.echo(f"Last failure: {last_failure_reason}")

if __name__ == "__main__":
    app()