import { useState, useEffect } from "react";
import {
  LineChart,
  Wallet,
  Activity,
  RefreshCw,
  Settings,
  Play,
  Square,
  Terminal,
} from "lucide-react";

// Constants
const API_URL = "http://127.0.0.1:8000/api"; // Dev URL

function App() {
  const [status, setStatus] = useState(null);
  const [positions, setPositions] = useState([]);
  const [activeTab, setActiveTab] = useState("dashboard");
  const [loading, setLoading] = useState(false);

  // Fetch Data
  const fetchData = async () => {
    setLoading(true);
    try {
      const s = await fetch(`${API_URL}/status`).then((res) => res.json());
      setStatus(s);

      const p = await fetch(`${API_URL}/positions`).then((res) => res.json());
      setPositions(p);
    } catch (e) {
      console.error("Fetch error", e);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 10000); // Poll every 10s
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="min-h-screen bg-gray-50 text-gray-900 font-sans">
      {/* Sidebar */}
      <aside className="fixed inset-y-0 left-0 w-64 bg-white border-r border-gray-200 z-10 flex flex-col">
        <div className="p-6 border-b border-gray-100 flex items-center gap-2">
          <LineChart className="w-6 h-6 text-blue-600" />
          <span className="font-bold text-xl tracking-tight">TradingBot</span>
        </div>

        <nav className="flex-1 p-4 space-y-1">
          <NavItem
            icon={<Wallet />}
            label="Dashboard"
            active={activeTab === "dashboard"}
            onClick={() => setActiveTab("dashboard")}
          />
          <NavItem
            icon={<Activity />}
            label="Positions"
            active={activeTab === "positions"}
            count={positions.length}
            onClick={() => setActiveTab("positions")}
          />
          <NavItem
            icon={<LineChart />}
            label="Chart"
            active={activeTab === "chart"}
            onClick={() => setActiveTab("chart")}
          />
          <NavItem
            icon={<Terminal />}
            label="Live Logs"
            active={activeTab === "logs"}
            onClick={() => setActiveTab("logs")}
          />
          <NavItem
            icon={<Settings />}
            label="Settings"
            active={activeTab === "settings"}
            onClick={() => setActiveTab("settings")}
          />
        </nav>

        <div className="p-4 border-t border-gray-100">
          <div className="flex items-center gap-2 px-4 py-2 bg-gray-100 rounded-lg">
            <div
              className={`w-2 h-2 rounded-full ${status?.status === "online" ? "bg-green-500" : "bg-red-500"}`}
            ></div>
            <span className="text-sm font-medium text-gray-600">
              {status?.status === "online" ? "Online" : "Offline"}
            </span>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="ml-64 p-8">
        <header className="mb-8 flex justify-between items-center">
          <h1 className="text-2xl font-bold text-gray-900 capitalize">
            {activeTab}
          </h1>
          <div className="flex gap-2">
            <button
              onClick={() => fetch(`${API_URL}/cron`)}
              className="flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium cursor-pointer"
            >
              <Play className="w-4 h-4" /> Run Scan
            </button>
            <button
              onClick={fetchData}
              className="p-2 hover:bg-gray-100 rounded-full transition-colors cursor-pointer"
            >
              <RefreshCw
                className={`w-5 h-5 text-gray-500 ${loading ? "animate-spin" : ""}`}
              />
            </button>
          </div>
        </header>

        {activeTab === "dashboard" && (
          <DashboardView status={status} positions={positions} />
        )}
        {activeTab === "positions" && <PositionsView positions={positions} />}
        {activeTab === "chart" && <ChartView />}
        {activeTab === "logs" && <LogsView />}
        {activeTab === "settings" && <SettingsView />}
      </main>
    </div>
  );
}

function NavItem({ icon, label, active, count, onClick }) {
  return (
    <button
      onClick={onClick}
      className={`w-full flex items-center justify-between px-4 py-3 rounded-lg text-sm font-medium transition-all cursor-pointer ${
        active ? "bg-blue-50 text-blue-700" : "text-gray-600 hover:bg-gray-50"
      }`}
    >
      <div className="flex items-center gap-3">
        {icon}
        <span>{label}</span>
      </div>
      {count !== undefined && count > 0 && (
        <span className="bg-blue-100 text-blue-700 py-0.5 px-2 rounded-full text-xs">
          {count}
        </span>
      )}
    </button>
  );
}

function DashboardView({ status, positions }) {
  const balance = status?.account?.accounts?.[0]?.balance?.available || 0;
  const total = status?.account?.accounts?.[0]?.balance?.total || 0;
  const currency = status?.account?.accounts?.[0]?.balance?.currency || "USD";

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <Card
          label="Available Cash"
          value={`${balance.toFixed(2)} ${currency}`}
          sub="Ready to trade"
        />
        <Card
          label="Total Equity"
          value={`${total.toFixed(2)} ${currency}`}
          sub="Cash + Open P&L"
        />
        <Card
          label="Active Trades"
          value={positions.length}
          sub="Open positions"
        />
      </div>

      <div className="bg-gradient-to-r from-blue-600 to-indigo-700 rounded-2xl p-8 text-white shadow-xl relative overflow-hidden">
        <div className="relative z-10">
          <h2 className="text-3xl font-bold mb-2">Bot is Active</h2>
          <p className="text-blue-100 mb-6">
            Scanning 50+ markets (Forex, Crypto, Indices) every minute.
          </p>
        </div>
      </div>
    </div>
  );
}

function Card({ label, value, sub }) {
  return (
    <div className="bg-white p-6 rounded-xl border border-gray-100 shadow-sm hover:shadow-md transition-shadow">
      <p className="text-sm text-gray-500 font-medium mb-1">{label}</p>
      <p className="text-3xl font-bold text-gray-900 tracking-tight">{value}</p>
      <p className="text-xs text-gray-400 mt-2">{sub}</p>
    </div>
  );
}

function PositionsView({ positions }) {
  if (positions.length === 0)
    return <div className="text-gray-500">No active positions.</div>;
  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden">
      <table className="w-full text-left text-sm">
        <thead className="bg-gray-50 border-b border-gray-100 text-gray-500 uppercase tracking-wider">
          <tr>
            <th className="px-6 py-3 font-medium">Market</th>
            <th className="px-6 py-3 font-medium">Size</th>
            <th className="px-6 py-3 font-medium">Direction</th>
            <th className="px-6 py-3 font-medium">P&L</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-100">
          {positions.map((p, i) => {
            const mkt = p.market || {};
            const pos = p.position || p;
            const ppl = pos.upl || 0;
            return (
              <tr key={i} className="hover:bg-gray-50 transition-colors">
                <td className="px-6 py-4 font-medium text-gray-900">
                  {mkt.api_epic || mkt.epic || pos.epic}
                </td>
                <td className="px-6 py-4 text-gray-600">
                  {pos.size || pos.dealSize}
                </td>
                <td className="px-6 py-4">
                  <span
                    className={`px-2 py-1 rounded-full text-xs font-medium ${pos.direction === "BUY" ? "bg-green-100 text-green-700" : "bg-red-100 text-red-700"}`}
                  >
                    {pos.direction}
                  </span>
                </td>
                <td
                  className={`px-6 py-4 font-bold ${ppl >= 0 ? "text-green-600" : "text-red-500"}`}
                >
                  {ppl}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

function ChartView() {
  useEffect(() => {
    // Prevent double injection
    if (document.getElementById("tv-script")) return;

    const script = document.createElement("script");
    script.id = "tv-script";
    script.src = "https://s3.tradingview.com/tv.js";
    script.async = true;
    script.onload = () => {
      if (window.TradingView) {
        new window.TradingView.widget({
          width: "100%",
          height: 600,
          symbol: "FX:EURUSD",
          interval: "5",
          timezone: "Etc/UTC",
          theme: "light",
          style: "1",
          locale: "en",
          toolbar_bg: "#f1f3f6",
          enable_publishing: false,
          allow_symbol_change: true,
          container_id: "tradingview_chart",
        });
      }
    };
    document.getElementById("tv-container").appendChild(script);
  }, []);

  return (
    <div className="bg-white p-4 rounded-xl border border-gray-200">
      <div id="tv-container">
        <div id="tradingview_chart"></div>
      </div>
    </div>
  );
}

function LogsView() {
  const [logs, setLogs] = useState([]);

  useEffect(() => {
    const fetchLogs = async () => {
      try {
        const res = await fetch(`${API_URL}/logs`).then((r) => r.json());
        setLogs(res);
      } catch (e) {
        console.error(e);
      }
    };
    fetchLogs();
    const interval = setInterval(fetchLogs, 2000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="bg-black text-green-400 font-mono text-sm p-4 rounded-xl h-[600px] overflow-y-auto shadow-inner">
      {logs.length === 0 && (
        <div className="text-gray-500">Waiting for logs...</div>
      )}
      {logs.map((log, i) => (
        <div key={i} className="mb-1 border-b border-gray-900 pb-1 break-words">
          <span className="opacity-50 mr-2">{log.split("]")[0]}]</span>
          <span>{log.split("]")[1] || log}</span>
        </div>
      ))}
    </div>
  );
}

function SettingsView() {
  const [settings, setSettings] = useState({
    broker: "capital",
    categories: [],
    risk: "medium",
  });

  useEffect(() => {
    fetch(`${API_URL}/settings`)
      .then((r) => r.json())
      .then(setSettings)
      .catch((e) => console.error(e));
  }, []);

  const save = async (newSettings) => {
    setSettings(newSettings);
    await fetch(`${API_URL}/settings`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(newSettings),
    });
  };

  const toggleCat = (cat) => {
    const cats = settings.categories || [];
    const newCats = cats.includes(cat)
      ? cats.filter((c) => c !== cat)
      : [...cats, cat];
    save({ ...settings, categories: newCats });
  };

  return (
    <div className="max-w-2xl space-y-8">
      <div className="bg-white p-6 rounded-xl border border-gray-200">
        <h3 className="text-lg font-bold mb-4">Broker Selection</h3>
        <div className="flex gap-4">
          <button
            onClick={() => save({ ...settings, broker: "capital" })}
            className={`flex-1 py-3 px-4 rounded-lg border text-center transition-all cursor-pointer ${settings.broker === "capital" ? "border-blue-500 bg-blue-50 text-blue-700 font-bold shadow-sm" : "border-gray-200 hover:bg-gray-50"}`}
          >
            Capital.com
          </button>
          <button
            onClick={() => save({ ...settings, broker: "t212" })}
            className={`flex-1 py-3 px-4 rounded-lg border text-center transition-all cursor-pointer ${settings.broker === "t212" ? "border-blue-500 bg-blue-50 text-blue-700 font-bold shadow-sm" : "border-gray-200 hover:bg-gray-50"}`}
          >
            Trading 212
          </button>
        </div>
      </div>

      <div className="bg-white p-6 rounded-xl border border-gray-200">
        <h3 className="text-lg font-bold mb-4">Active Markets</h3>
        <div className="grid grid-cols-2 gap-3">
          {["Forex", "Crypto", "Indices", "Commodities", "US Stocks"].map(
            (cat) => (
              <label
                key={cat}
                className="flex items-center gap-3 p-3 border border-gray-100 rounded-lg hover:bg-gray-50 cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={settings.categories?.includes(cat)}
                  onChange={() => toggleCat(cat)}
                  className="w-5 h-5 text-blue-600 rounded focus:ring-blue-500 cursor-pointer"
                />
                <span className="font-medium text-gray-700">{cat}</span>
              </label>
            ),
          )}
        </div>
      </div>

      <div className="bg-white p-6 rounded-xl border border-gray-200">
        <h3 className="text-lg font-bold mb-4">Risk Management</h3>
        <p className="text-sm text-gray-500 mb-4">
          Select risk profile for position sizing.
        </p>
        <select
          value={settings.risk}
          onChange={(e) => save({ ...settings, risk: e.target.value })}
          className="w-full p-2 border border-gray-200 rounded-lg cursor-pointer"
        >
          <option value="low">Low (Conservative)</option>
          <option value="medium">Medium (Balanced)</option>
          <option value="high">High (Aggressive)</option>
        </select>
      </div>
    </div>
  );
}

export default App;
