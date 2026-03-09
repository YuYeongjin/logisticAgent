import { useState, useEffect, useRef, useMemo, useCallback } from "react";
import DashboardAPI from "./DashboardAPI";
import TelemetryGraph from "./graph/Graph";
import './Dashboard.css';
/* =======================
   Constants & Styles
======================= */
const statusStyles = {
    info: { color: "#4caf50", bg: "rgba(76, 175, 80, 0.1)", border: "#4caf50" },
    warn: { color: "#ff9800", bg: "rgba(255, 152, 0, 0.1)", border: "#ff9800" },
    danger: { color: "#f44336", bg: "rgba(244, 67, 54, 0.1)", border: "#f44336" },
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
        isAutoCapturing,
        setIsAutoCapturing,
        captureInterval,
        setCaptureInterval,
        captureAndSend,
        latestSensor,
        envData,
        logData,
        imageList,
        currentTime,
        videoRefs,
        cameras,
        tempMin, setTempMin,
        tempMax, setTempMax,
        humMin, setHumMax,
        humMax, setHumMin,
        isTempAlarm,
        isHumAlarm
    } = DashboardAPI();

    return (
        <div style={{ background: "#0f0f12", minHeight: "100vh", color: "#fff", padding: "40px" }}>
            <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "30px", borderBottom: "1px solid #222", paddingBottom: "20px" }}>
                <div>
                    <h1 style={{ margin: 0, fontSize: "28px", letterSpacing: "-1px" }}>VENETA REAL-TIME MONITORING</h1>
                    <p style={{ color: "#888", margin: "5px 0 0" }}>Logistics Center Management System</p>
                </div>
                <div style={{ textAlign: "right", display: 'flex', alignItems: 'center', gap: '20px' }}>
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
                    <div style={{ display: 'flex', gap: '20px', marginBottom: '40px' }}>
                        {/* 1. 좌측 절반: 라이브 카메라 피드 (사이즈 축소) */}
                        <div style={{ flex: 1, display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", gap: "15px" }}>
                            <h3 style={{ gridColumn: "1 / -1", display: "flex", alignItems: "center", gap: "8px", marginBottom: "5px", fontSize: "16px" }}>
                                <span style={{ width: "8px", height: "8px", background: "#00d1ff", borderRadius: "50%" }}></span>
                                LIVE FEEDS
                            </h3>
                            {cameras.map(cam => (
                                <div key={cam.id} style={{ background: "#1e1e2d", borderRadius: "12px", overflow: "hidden", border: `2px solid ${cam.color}`, position: "relative" }}>
                                    <div style={{ aspectRatio: "16/9", background: "#000" }}>
                                        <video
                                            ref={el => videoRefs.current[cam.id] = el}
                                            autoPlay playsInline muted
                                            style={{ width: "100%", height: "100%", objectFit: "cover" }}
                                        />
                                        <div style={{ position: "absolute", top: "5px", right: "5px", background: cam.color, padding: "2px 6px", borderRadius: "4px", fontSize: "9px", fontWeight: "bold" }}>
                                            CAM {cam.id}
                                        </div>
                                    </div>
                                </div>
                            ))}
                        </div>

                        {/* 2. 우측 절반: 캡처 이미지 히스토리 (새로 추가) */}
                        <div style={{ flex: 1, background: "#1e1e2d", borderRadius: "12px", border: "1px solid #333", display: "flex", flexDirection: "column", overflow: "hidden" }}>
                            <div style={{ padding: "15px", borderBottom: "1px solid #333", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                                <h3 style={{ margin: 0, fontSize: "15px", color: "#6366f1", display: "flex", alignItems: "center", gap: "8px" }}>
                                    <span style={{ width: "8px", height: "8px", background: "#6366f1", borderRadius: "50%" }}></span>
                                    CAPTURE HISTORY
                                </h3>
                                <span style={{ fontSize: "11px", color: "#64748B" }}> 최근 24시간 {imageList && imageList.length}</span>
                            </div>

                            <div style={{
                                background: "#1e1e2d",
                                borderRadius: "12px",
                                // padding: "20px",/
                                minHeight: "27vh", // 위 섹션과 균형을 맞춰 고정
                                border: "1px solid #333",
                                overflowY: 'auto'
                            }}>
                                {/* imageList가 비어있을 경우 대응 */}
                                {!imageList || imageList.length === 0 ? (
                                    <div style={{ textAlign: 'center', color: '#444', marginTop: '20%' }}>No images captured yet.</div>
                                ) : (
                                    <div style={{ display: "grid", gridTemplateColumns: "repeat(2, 1fr)", gap: "10px" }}>
                                        {imageList.map((img, idx) => (
                                            <div key={idx} style={{ borderRadius: "8px", overflow: "hidden", border: "1px solid #333", background: "#0f0f12", position: "relative" }}>
                                                <img src={img.url} alt="captured" style={{ width: "100%", aspectRatio: "16/9", objectFit: "cover" }} />
                                                <div style={{
                                                    position: "absolute", bottom: 0, width: "100%",
                                                    background: "rgba(0,0,0,0.7)", color: "#fff",
                                                    fontSize: "10px", padding: "4px", textAlign: "center",
                                                    display: "flex", justifyContent: "space-between"
                                                }}>
                                                    <span>{img.name && (img.name).substring(0, 5)}</span>
                                                    <span>{img.time}</span>
                                                </div>
                                            </div>
                                        ))}
                                    </div>
                                )}
                            </div>
                        </div>
                    </div>
                    <div className="sensor-card">

                        <div className="sensor-header">
                            <h3>REAL-TIME SENSOR TELEMETRY</h3>

                            <div className="sensor-values">
                                <div className={isTempAlarm ? "danger" : "temp"}>
                                    온도 {latestSensor?.temperature?.toFixed(1)} °C
                                </div>

                                <div className={isHumAlarm ? "danger" : "hum"}>
                                    습도 {latestSensor?.humidity?.toFixed(1)} %
                                </div>
                            </div>
                        </div>

                        <div className="control-row">

                            {/* 온도 */}
                            <div className="control-box temp-slider">
                                <div className="label">
                                    온도 기준
                                    <span>{tempMin}°C ~ {tempMax}°C</span>
                                </div>

                                <div className="slider-row">
                                    <input                           
                                        type="range"
                                        min="0"
                                        max="50"
                                        value={tempMin}
                                        onChange={(e) => setTempMin(Number(e.target.value))}
                                    />

                                    <input
                                        type="range"
                                        min="0"
                                        max="50"
                                        value={tempMax}
                                        onChange={(e) => setTempMax(Number(e.target.value))}
                                    />
                                </div>
                            </div>

                            {/* 습도 */}
                            <div className="control-box">
                                <div className="label">
                                    습도 기준
                                    <span>{humMin}% ~ {humMax}%</span>
                                </div>

                                <div className="slider-row hum-slider">
                                    <input
                                        type="range"
                                        min="0"
                                        max="100"
                                        value={humMin}
                                        onChange={(e) => setHumMin(Number(e.target.value))}
                                    />

                                    <input
                                        type="range"
                                        min="0"
                                        max="100"
                                        value={humMax}
                                        onChange={(e) => setHumMax(Number(e.target.value))}
                                    />
                                </div>
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
                    <div style={{
                        background: "#1e1e2d",
                        borderRadius: "12px",
                        padding: "20px",
                        minHeight: "43vh", // 화면 높이의 약 절반으로 고정
                        maxHeight: "65vh", // 화면 높이의 약 절반으로 고정
                        border: "1px solid #333",
                        overflowY: 'auto', // 내용이 길어지면 드래그 가능
                        scrollbarWidth: 'thin' // 스크롤바를 얇게 (선택사항)
                    }}>
                        {logData && logData.map((n, idx) => (
                            <div key={idx} style={{
                                marginBottom: "15px", padding: "15px", borderRadius: "8px",
                                background: statusStyles[n.log_level]?.bg || "rgba(255,255,255,0.05)",
                                borderLeft: `4px solid ${statusStyles[n.log_level]?.border || "#888"}`
                            }}>
                                <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "8px" }}>
                                    <span style={{ fontSize: "11px", fontWeight: "bold", color: statusStyles[n.log_level]?.color }}>{n.log_level}</span>
                                    <span style={{ fontSize: "11px", color: "#666" }}>{n.time}</span>
                                </div>
                                <div style={{ fontSize: "13px", lineHeight: "1.5", color: "#ddd" }}>{n.response}</div>
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