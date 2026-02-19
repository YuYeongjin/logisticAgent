import { useState, useEffect, useRef, useMemo } from "react";

/* =======================
   Constants & Styles
======================= */
const statusStyles = {
    NORMAL: { color: "#4caf50", bg: "rgba(76, 175, 80, 0.1)", border: "#4caf50" },
    NOTICE: { color: "#ff9800", bg: "rgba(255, 152, 0, 0.1)", border: "#ff9800" },
    WARNING: { color: "#f44336", bg: "rgba(244, 67, 54, 0.1)", border: "#f44336" },
};

/* =======================
   TelemetryGraph (SVG)
======================= */
function TelemetryGraph({ data }) {
    const width = 800;
    const height = 250;
    const pL = 50, pB = 40, pT = 20, pR = 20;
    const cW = width - pL - pR, cH = height - pB - pT;
    const maxVal = 100;

    const getX = (i) => pL + (i / (data.length - 1)) * cW;
    const getY = (v) => height - pB - (v / maxVal) * cH;

    const { tempPath, humPath, tempArea, humArea } = useMemo(() => {
        if (data.length === 0) return { tempPath: "", humPath: "", tempArea: "", humArea: "" };
        const tPath = data.map((d, i) => `${i === 0 ? "M" : "L"} ${getX(i)} ${getY(d.temperature)}`).join(" ");
        const hPath = data.map((d, i) => `${i === 0 ? "M" : "L"} ${getX(i)} ${getY(d.humidity)}`).join(" ");
        const tArea = `${tPath} L ${getX(data.length - 1)} ${getY(0)} L ${getX(0)} ${getY(0)} Z`;
        const hArea = `${hPath} L ${getX(data.length - 1)} ${getY(0)} L ${getX(0)} ${getY(0)} Z`;
        return { tempPath: tPath, humPath: hPath, tempArea: tArea, humArea: hArea };
    }, [data]);

    return (
        <div className="w-full p-4 bg-gray-950/50 rounded-xl border border-gray-800">
            <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto">
                {/* Y-Axis Labels & Grid */}
                {[0, 25, 50, 75, 100].map(v => (
                    <g key={v}>
                        <text x={pL - 10} y={getY(v) + 4} fill="#555" fontSize="11" textAnchor="end">{v}</text>
                        <line x1={pL} y1={getY(v)} x2={width - pR} y2={getY(v)} stroke="#222" strokeDasharray="4" />
                    </g>
                ))}
                {/* X-Axis Labels (최신 5개 시간대만 표시하여 가독성 확보) */}
                {data.map((d, i) => i % 10 === 0 ? (
                    <text key={i} x={getX(i)} y={height - 10} fill="#555" fontSize="10" textAnchor="middle">{d.time}</text>
                ) : null)}
                
                <defs>
                    <linearGradient id="gT" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#fb923c" stopOpacity="0.2" /><stop offset="100%" stopColor="transparent" /></linearGradient>
                    <linearGradient id="gH" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#60a5fa" stopOpacity="0.2" /><stop offset="100%" stopColor="transparent" /></linearGradient>
                </defs>
                <path d={tempArea} fill="url(#gT)" stroke="none" />
                <path d={humArea} fill="url(#gH)" stroke="none" />
                <path d={tempPath} fill="none" stroke="#fb923c" strokeWidth="2.5" />
                <path d={humPath} fill="none" stroke="#60a5fa" strokeWidth="2.5" />
            </svg>
        </div>
    );
}

/* =======================
   WebCam Component
======================= */
function WebCam({ name, status, color }) {
    const videoRef = useRef(null);
    useEffect(() => {
        if (navigator.mediaDevices && navigator.mediaDevices.getUserMedia) {
            navigator.mediaDevices.getUserMedia({ video: true })
                .then((stream) => { if (videoRef.current) videoRef.current.srcObject = stream; })
                .catch((err) => console.error("카메라 권한 거부:", err));
        }
    }, []);

    return (
        <div style={{ flex: 1, background: "#1e1e2d", borderRadius: "12px", overflow: "hidden", border: `2px solid ${color}`, boxShadow: `0 10px 30px ${color}33` }}>
            <div style={{ position: "relative", backgroundColor: "#000", aspectRatio: "16/9" }}>
                <video ref={videoRef} autoPlay playsInline muted style={{ width: "100%", height: "100%", objectFit: "cover" }} />
                <div style={{ position: "absolute", top: "10px", right: "10px", background: color, padding: "4px 8px", borderRadius: "4px", fontSize: "10px", fontWeight: "900" }}>LIVE</div>
            </div>
            <div style={{ padding: "15px" }}>
                <div style={{ fontWeight: "bold", marginBottom: "5px" }}>{name}</div>
                <div style={{ color, fontSize: "12px", fontWeight: "bold" }}>STATUS: {status}</div>
            </div>
        </div>
    );
}

/* =======================
   Main Dashboard
======================= */
export default function Dashboard() {
    const [notices] = useState([
        { time: "10:12:45", level: "WARNING", message: "2번 카메라 적재물 위치 변화 감지 (심각)" },
        { time: "09:58:22", level: "NOTICE", message: "B구역 온도 임계치(28도) 근접 알림" },
        { time: "09:40:05", level: "INFO", message: "전체 시스템 보안 스캔 완료" },
    ]);

    // 1. 초기 50개의 더미 데이터 생성
    const [envData, setEnvData] = useState(() => 
        Array.from({ length: 50 }).map((_, i) => ({
            time: new Date(Date.now() - (50 - i) * 1000).toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }),
            temperature: 20 + Math.random() * 5,
            humidity: 45 + Math.random() * 10,
        }))
    );

    const [currentTime, setCurrentTime] = useState(new Date().toLocaleTimeString());

    // 2. 실시간 데이터 스트리밍 Effect
    useEffect(() => {
        const timer = setInterval(() => {
            const now = new Date();
            setCurrentTime(now.toLocaleTimeString());

            // 새로운 센서 데이터 생성 (실제 API 연결 시 이 부분을 fetch로 교체)
            const newData = {
                time: now.toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' }),
                temperature: 22 + Math.random() * 4, // 22~26도 사이 랜덤
                humidity: 50 + Math.random() * 8,    // 50~58% 사이 랜덤
            };

            // 기존 배열에서 앞을 하나 빼고 뒤에 하나를 추가 (Queue 방식)
            setEnvData(prev => [...prev.slice(1), newData]);
        }, 1000); // 1초마다 업데이트

        return () => clearInterval(timer);
    }, []);

    const cameras = [
        { id: 1, name: "1번 작업", status: "NORMAL", color: "#4caf50", isLocal: false, url: "https://via.placeholder.com/300x180/1a1a1a/ffffff?text=CAM+01" },
        { id: 2, name: "2번 작업", status: "NOTICE", color: "#ff9800", isLocal: false, url: "https://via.placeholder.com/300x180/1a1a1a/ffffff?text=CAM+02" },
        { id: 3, name: "맥북 카메라 (현장 점검)", status: "WARNING", color: "#f44336", isLocal: true }
    ];

    return (
        <div style={{ background: "#0f0f12", minHeight: "100vh", color: "#fff", padding: "40px" }}>
            <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "30px", borderBottom: "1px solid #222", paddingBottom: "20px" }}>
                <div>
                    <h1 style={{ margin: 0, fontSize: "28px", letterSpacing: "-1px" }}>VENETA REAL-TIME MONITORING</h1>
                    <p style={{ color: "#888", margin: "5px 0 0" }}>Logistics Center Management System</p>
                </div>
                <div style={{ textAlign: "right" }}>
                    <div style={{ fontSize: "20px", fontWeight: "600", color: "#00d1ff" }}>{currentTime}</div>
                    <div style={{ color: "#4caf50", fontSize: "13px" }}>● SENSORS CONNECTED</div>
                </div>
            </header>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 350px", gap: "24px" }}>
                <section>
                    <h3 style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "20px" }}>
                        <span style={{ width: "8px", height: "8px", background: "#00d1ff", borderRadius: "50%" }}></span>
                        LIVE CAMERA FEED
                    </h3>
                    <div style={{ display: "flex", gap: "20px", marginBottom: "40px" }}>
                        {cameras.map(cam => (
                            cam.isLocal ? (
                                <WebCam key={cam.id} name={cam.name} status={cam.status} color={cam.color} />
                            ) : (
                                <div key={cam.id} style={{ flex: 1, background: "#1e1e2d", borderRadius: "12px", overflow: "hidden", border: `2px solid ${cam.color}` }}>
                                    <img src={cam.url} alt="" style={{ width: "100%" }} />
                                    <div style={{ padding: "15px" }}>
                                        <b>{cam.name}</b>
                                        <div style={{ color: cam.color, fontSize: "12px" }}>{cam.status}</div>
                                    </div>
                                </div>
                            )
                        ))}
                    </div>
                    
                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
                        <h3 style={{ display: "flex", alignItems: "center", gap: "8px", margin: 0 }}>
                            <span style={{ width: "8px", height: "8px", background: "#f44336", borderRadius: "50%" }}></span>
                            REAL-TIME SENSOR TELEMETRY (1s Update)
                        </h3>
                        <div style={{ display: 'flex', gap: '15px', fontSize: '11px' }}>
                            <span style={{ color: '#fb923c' }}>● TEMP: {envData[envData.length-1].temperature.toFixed(1)}°C</span>
                            <span style={{ color: '#60a5fa' }}>● HUM: {envData[envData.length-1].humidity.toFixed(1)}%</span>
                        </div>
                    </div>
                    <TelemetryGraph data={envData} />
                </section>

                <aside>
                    <h3 style={{ display: "flex", alignItems: "center", gap: "8px", marginBottom: "20px" }}>
                        <span style={{ width: "8px", height: "8px", background: "#ff9800", borderRadius: "50%" }}></span>
                        EVENT LOGS
                    </h3>
                    <div style={{ background: "#1e1e2d", borderRadius: "12px", padding: "20px", height: "calc(100% - 60px)", border: "1px solid #333", overflowY: 'auto' }}>
                        {notices.map((n, idx) => (
                            <div key={idx} style={{ marginBottom: "15px", padding: "15px", borderRadius: "8px", background: statusStyles[n.level]?.bg || "rgba(255,255,255,0.05)", borderLeft: `4px solid ${statusStyles[n.level]?.border || "#888"}` }}>
                                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
                                    <span style={{ fontSize: "11px", fontWeight: "bold", color: statusStyles[n.level]?.color }}>{n.level}</span>
                                    <span style={{ fontSize: "11px", color: "#666" }}>{n.time}</span>
                                </div>
                                <div style={{ fontSize: "13px", lineHeight: "1.5", color: "#ddd" }}>{n.message}</div>
                            </div>
                        ))}
                    </div>
                </aside>
            </div>
        </div>
    );
}