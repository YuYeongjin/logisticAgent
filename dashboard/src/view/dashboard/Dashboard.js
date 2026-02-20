import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import DashboardAPI from "./DashboardAPI";
import TelemetryGraph from "./graph/Graph";

/* =======================
   Constants & Styles
======================= */
const statusStyles = {
    NORMAL: { color: "#4caf50", bg: "rgba(76, 175, 80, 0.1)", border: "#4caf50" },
    NOTICE: { color: "#ff9800", bg: "rgba(255, 152, 0, 0.1)", border: "#ff9800" },
    WARNING: { color: "#f44336", bg: "rgba(244, 67, 54, 0.1)", border: "#f44336" },
};


/* =======================
   WebCam Component
======================= */
const WebCam = ({ name, status, color, videoRef }) => {
    return (
        <div style={{ flex: 1, background: "#1e1e2d", borderRadius: "12px", overflow: "hidden", border: `2px solid ${color}`, boxShadow: `0 10px 30px ${color}33` }}>
            <div style={{ position: "relative", backgroundColor: "#000", aspectRatio: "16/9" }}>
                {/* DashboardAPI에서 제공하는 videoRef를 연결합니다 */}
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
    const {
        videoRef,
        getCameraStream,
        isAutoCapturing,
        setIsAutoCapturing,
        captureInterval,
        setCaptureInterval,
        captureAndSend,
        sensorData,
        latestSensor,
        envData,
    } = DashboardAPI();

    const [notices] = useState([
        { time: "10:12:45", level: "WARNING", message: "2번 카메라 적재물 위치 변화 감지 (심각)" },
        { time: "09:58:22", level: "NOTICE", message: "B구역 온도 임계치(28도) 근접 알림" },
        { time: "09:40:05", level: "INFO", message: "전체 시스템 보안 스캔 완료" },
    ]);
    const videoRefs = useRef({});

    const cameras = [
        { id: 1, name: "1번 작업", status: "NORMAL", color: "#4caf50", isLocal: false, url: "https://via.placeholder.com/300x180/1a1a1a/ffffff?text=CAM+01" },
        { id: 2, name: "2번 작업", status: "NOTICE", color: "#ff9800", isLocal: false, url: "https://via.placeholder.com/300x180/1a1a1a/ffffff?text=CAM+02" },
        { id: 3, name: "3번 작업", status: "WARNING", color: "#f44336", isLocal: true }
    ];
    useEffect(() => {
        const setupCameras = async () => {
            const stream = await getCameraStream();
            if (stream) {
                // 정의된 모든 로컬 카메라 video 태그에 동일 스트림 할당
                // (나중에 여러 대의 웹캠을 쓸 경우 여기서 장치별로 할당 가능)
                cameras.forEach(cam => {
                    const videoEl = videoRefs.current[cam.id];
                    if (videoEl) {
                        videoEl.srcObject = stream;
                    }
                });
            }
        };
        setupCameras();
    }, []);
    useEffect(() => {
        let intervalId;
        if (isAutoCapturing) {
            intervalId = setInterval(() => {
                cameras.forEach(cam => {
                    const videoEl = videoRefs.current[cam.id];
                    if (videoEl && videoEl.readyState >= 2) {                    

                        captureAndSend(cam.id, videoEl);
                    }
                });
            }, captureInterval * 1000);
        }
        return () => clearInterval(intervalId);
    }, [isAutoCapturing, captureInterval, captureAndSend]);

    useEffect(() => {
        const timer = setInterval(() => {
            setCurrentTime(new Date().toLocaleTimeString());
        }, 1000);
        return () => clearInterval(timer);
    }, []);

    const [currentTime, setCurrentTime] = useState(new Date().toLocaleTimeString());

    return (
        <div style={{ background: "#0f0f12", minHeight: "100vh", color: "#fff", padding: "40px" }}>
            <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "30px", borderBottom: "1px solid #222", paddingBottom: "20px" }}>
                <div>
                    <h1 style={{ margin: 0, fontSize: "28px", letterSpacing: "-1px" }}>VENETA REAL-TIME MONITORING</h1>
                    <p style={{ color: "#888", margin: "5px 0 0" }}>Logistics Center Management System</p>
                </div>
                <div style={{ textAlign: "right", display: 'flex', alignItems: 'center', gap: '20px' }}>
                    {/* 자동 촬영 컨트롤러 UI 추가 */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px', background: '#1e1e2d', padding: '8px 15px', borderRadius: '10px', border: '1px solid #333' }}>
                        <span style={{ fontSize: '12px', color: '#888' }}>AUTO CAPTURE:</span>
                        <input
                            type="number"
                            value={captureInterval}
                            onChange={(e) => setCaptureInterval(Number(e.target.value))}
                            style={{ width: '50px', background: '#0f0f12', border: '1px solid #444', color: '#00d1ff', textAlign: 'center', borderRadius: '4px', fontSize: '12px' }}
                        />
                        <span style={{ fontSize: '12px', color: '#888' }}>sec</span>
                        <button
                            onClick={() => setIsAutoCapturing(!isAutoCapturing)}
                            style={{
                                padding: '4px 10px',
                                borderRadius: '5px',
                                fontSize: '10px',
                                fontWeight: 'bold',
                                cursor: 'pointer',
                                background: isAutoCapturing ? '#f44336' : '#4caf50',
                                border: 'none',
                                color: 'white'
                            }}
                        >
                            {isAutoCapturing ? "STOP" : "START"}
                        </button>
                    </div>
                    <div>
                        <div style={{ fontSize: "20px", fontWeight: "600", color: "#00d1ff" }}>{currentTime}</div>
                        <div style={{ color: "#4caf50", fontSize: "13px" }}>● SENSORS CONNECTED</div>
                    </div>
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
                            <div key={cam.id} style={{ flex: 1, background: "#1e1e2d", borderRadius: "12px", overflow: "hidden", border: `2px solid ${cam.color}` }}>
                                <div style={{ position: "relative", aspectRatio: "16/9", background: "#000" }}>
                                    <video
                                        ref={el => videoRefs.current[cam.id] = el}
                                        autoPlay playsInline muted
                                        style={{ width: "100%", height: "100%", objectFit: "cover" }}
                                    />
                                    <div style={{ position: "absolute", top: "10px", right: "10px", background: cam.color, padding: "4px 8px", borderRadius: "4px", fontSize: "10px" }}>
                                        CAM {cam.id} LIVE
                                    </div>
                                </div>
                                <div style={{ padding: "15px" }}>
                                    <b>{cam.name}</b>
                                </div>
                            </div>
                        ))}
                    </div>

                    <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
                        <h3 style={{ display: "flex", alignItems: "center", gap: "8px", margin: 0 }}>
                            <span style={{ width: "8px", height: "8px", background: "#f44336", borderRadius: "50%" }}></span>
                            REAL-TIME SENSOR TELEMETRY (2s Update)
                        </h3>
                        <div style={{ display: "flex", gap: 20, marginBottom: 20 }}>
                            <div style={{ color: "#fb923c" }}>
                                ● 온도: {latestSensor?.temperature?.toFixed(1) ?? "-"} °C
                            </div>
                            <div style={{ color: "#60a5fa" }}>
                                ● 습도: {latestSensor?.humidity?.toFixed(1) ?? "-"} %
                            </div>
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

            {/* 수동 촬영 테스트용 플로팅 버튼 (개발 단계 확인용) */}
            <button
                onClick={captureAndSend}
                style={{ position: 'fixed', bottom: '30px', right: '30px', width: '50px', height: '50px', borderRadius: '25px', background: '#6366f1', border: 'none', color: 'white', fontSize: '20px', cursor: 'pointer', boxShadow: '0 5px 15px rgba(0,0,0,0.3)' }}
            >
                📸
            </button>
        </div>
    );
}