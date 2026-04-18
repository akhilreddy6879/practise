import express from "express";
import fetch from "node-fetch";
import fs from "fs";
import yaml from "js-yaml";

const app = express();
const port = 4000;
const GITHUB_API = "https://api.github.com";
const token = process.env.GITHUB_TOKEN;

if (!token) {
  throw new Error("GITHUB_TOKEN not set");
}

// Load services.yml from repo root
const services = yaml.load(
  fs.readFileSync(new URL("../services.yml", import.meta.url), "utf8")
).services;

// simple in-memory rate limit: max 50 calls/minute
let calls = 0;
setInterval(() => { calls = 0; }, 60_000);

async function ghRequest(path, params = {}) {
  if (calls > 50) {
    throw new Error("Local rate limit exceeded");
  }
  calls++;

  const url = new URL(GITHUB_API + path);
  Object.entries(params).forEach(([k, v]) =>
    url.searchParams.set(k, v)
  );

  const res = await fetch(url, {
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
    },
  });

  if (!res.ok) {
    const text = await res.text();
    throw new Error(`GitHub error ${res.status}: ${text}`);
  }
  return res.json();
}

// GET /api/health - summary for all services
app.get("/api/health", async (req, res) => {
  try {
    const results = await Promise.all(
      Object.entries(services).map(async ([name, svc]) => {
        const data = await ghRequest(
          `/repos/${svc.owner}/${svc.repo}/actions/workflows/${svc.workflow}/runs`,
          { per_page: 10 }
        );
        const runs = data.workflow_runs || [];

        if (runs.length === 0) {
          return {
            name,
            repo: `${svc.owner}/${svc.repo}`,
            status: "unknown",
            lastRunStatus: null,
            lastRunAt: null,
            successRate: 0,
          };
        }

        const total = runs.length;
        const successes = runs.filter(r => r.conclusion === "success").length;
        const successRate = (successes / total) * 100;

        const last = runs[0];
        let status;
        if (successes === total) status = "healthy";
        else if (successes === 0) status = "failing";
        else status = "degraded";

        return {
          name,
          repo: `${svc.owner}/${svc.repo}`,
          status,
          lastRunStatus: last.conclusion,
          lastRunAt: last.created_at,
          successRate,
        };
      })
    );

    res.json(results);
  } catch (e) {
    console.error(e);
    res.status(500).json({ error: e.message });
  }
});

app.get("/dashboard", (req, res) => {
    res.send(`
      <!DOCTYPE html>
      <html>
        <head>
          <title>Pipeline Health Dashboard</title>
          <style>
            body { font-family: Arial, sans-serif; padding: 20px; }
            table { border-collapse: collapse; width: 100%; margin-top: 20px; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #f2f2f2; }
            .status-healthy { color: green; font-weight: bold; }
            .status-degraded { color: orange; font-weight: bold; }
            .status-failing { color: red; font-weight: bold; }
            .status-unknown { color: gray; }
          </style>
        </head>
        <body>
          <h1>Pipeline Health Dashboard</h1>
          <p>Data from GitHub Actions via <code>/api/health</code>.</p>
  
          <table id="health-table">
            <thead>
              <tr>
                <th>Service</th>
                <th>Repository</th>
                <th>Status</th>
                <th>Last Run Status</th>
                <th>Last Run At</th>
                <th>Success Rate (%)</th>
              </tr>
            </thead>
            <tbody>
              <tr><td colspan="6">Loading...</td></tr>
            </tbody>
          </table>
  
          <script>
            async function loadHealth() {
              try {
                const res = await fetch('/api/health');
                if (!res.ok) {
                  throw new Error('HTTP ' + res.status);
                }
                const data = await res.json();
                const tbody = document.querySelector('#health-table tbody');
                tbody.innerHTML = '';
  
                if (!data || data.length === 0) {
                  tbody.innerHTML = '<tr><td colspan="6">No data</td></tr>';
                  return;
                }
  
                for (const svc of data) {
                  const tr = document.createElement('tr');
  
                  const statusClass = 'status-' + (svc.status || 'unknown');
  
                  tr.innerHTML = \`
                    <td>\${svc.name}</td>
                    <td>\${svc.repo}</td>
                    <td class="\${statusClass}">\${svc.status}</td>
                    <td>\${svc.lastRunStatus ?? ''}</td>
                    <td>\${svc.lastRunAt ?? ''}</td>
                    <td>\${svc.successRate.toFixed(1)}</td>
                  \`;
  
                  tbody.appendChild(tr);
                }
              } catch (err) {
                const tbody = document.querySelector('#health-table tbody');
                tbody.innerHTML = '<tr><td colspan="6">Error loading data: ' + err.message + '</td></tr>';
              }
            }
  
            loadHealth();
            // Optional auto-refresh every 60s
            setInterval(loadHealth, 60000);
          </script>
        </body>
      </html>
    `);
  });

app.listen(port, () => {
  console.log(`Dashboard API listening on http://localhost:${port}`);
});