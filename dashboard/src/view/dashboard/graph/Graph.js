import React, { useMemo } from "react";

export default function TelemetryGraph({ data }) {
    const width = 900;
    const height = 280;
    const pL = 50, pR = 20, pT = 30, pB = 40;
    const cW = width - pL - pR;
    const cH = height - pT - pB;

    const chartMetrics = useMemo(() => {
        if (!data || data.length < 2) return null;

        const temps = data.map(d => d.temperature);
        const hums = data.map(d => d.humidity);
        
        // 1️⃣ Y축 범위를 데이터보다 훨씬 여유있게 설정 (요동 방지)
        // 습도와 온도가 모두 포함되도록 하되, 최소 범위를 10 이상으로 강제합니다.
        const rawMin = Math.min(...temps, ...hums);
        const rawMax = Math.max(...temps, ...hums);
        
        // 데이터가 30 근처라면 최소 20 ~ 최대 40 정도로 보이게 설정
        const minVal = Math.floor(rawMin - 5); 
        const maxVal = Math.ceil(rawMax + 5);
        
        // 만약 데이터 변화가 너무 적어 range가 작으면 강제로 늘림 (변동폭 완화)
        const range = (maxVal - minVal) < 10 ? 10 : (maxVal - minVal);

        const getX = (index) => pL + (index / (data.length - 1)) * cW;
        const getY = (v) => height - pB - ((v - minVal) / range) * cH;

        const tPoints = data.map((d, i) => `${getX(i)},${getY(d.temperature)}`).join(" L ");
        const hPoints = data.map((d, i) => `${getX(i)},${getY(d.humidity)}`).join(" L ");
        
        const baseY = getY(minVal);
        const startX = getX(0);
        const endX = getX(data.length - 1);

        // 눈금을 5단위로 깔끔하게 떨어지게 계산
        const yTicks = Array.from({ length: 5 }, (_, i) => minVal + (range / 4) * i);

        return {
            tempPath: `M ${tPoints}`,
            humPath: `M ${hPoints}`,
            tempArea: `M ${startX},${baseY} L ${tPoints} L ${endX},${baseY} Z`,
            humArea: `M ${startX},${baseY} L ${hPoints} L ${endX},${baseY} Z`,
            yTicks,
            getY,
            getX
        };
    }, [data, cW, cH]);

    if (!chartMetrics) {
        return (
            <div style={{ width: '100%', height: '280px', display: 'flex', alignItems: 'center', justifyContent: 'center', background: '#11111b', borderRadius: '15px', color: '#555' }}>
                데이터 수집 중...
            </div>
        );
    }

    const { tempPath, humPath, tempArea, humArea, yTicks, getY, getX } = chartMetrics;

    return (
        <div style={{ width: '100%', padding: '20px', background: '#11111b', borderRadius: '15px', border: '1px solid #222' }}>
            <svg viewBox={`0 0 ${width} ${height}`} style={{ width: '100%', height: 'auto', overflow: 'visible' }}>
                <defs>
                    <linearGradient id="gTemp" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#fb923c" stopOpacity="0.2" />
                        <stop offset="100%" stopColor="#fb923c" stopOpacity="0" />
                    </linearGradient>
                    <linearGradient id="gHum" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#60a5fa" stopOpacity="0.2" />
                        <stop offset="100%" stopColor="#60a5fa" stopOpacity="0" />
                    </linearGradient>
                </defs>

                {/* Y Grid Lines */}
                {yTicks.map((v, i) => (
                    <g key={i}>
                        <line x1={pL} y1={getY(v)} x2={width - pR} y2={getY(v)} stroke="#222" strokeWidth="1" />
                        <text x={pL - 10} y={getY(v) + 4} fontSize="11" fill="#666" textAnchor="end">{v.toFixed(1)}</text>
                    </g>
                ))}

                {/* X Labels */}
                {data.map((d, i) => 
                    (i % Math.floor(data.length / 5) === 0) ? (
                        <text key={i} x={getX(i)} y={height - 10} fontSize="10" fill="#666" textAnchor="middle">{d.time}</text>
                    ) : null
                )}

                {/* Areas */}
                <path d={tempArea} fill="url(#gTemp)" style={{ transition: 'all 0.5s ease-in-out' }} />
                <path d={humArea} fill="url(#gHum)" style={{ transition: 'all 0.5s ease-in-out' }} />

                {/* Lines (Stroke를 더 굵게 하여 안정감 부여) */}
                <path d={tempPath} fill="none" stroke="#fb923c" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" style={{ transition: 'all 0.5s ease-in-out' }} />
                <path d={humPath} fill="none" stroke="#60a5fa" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" style={{ transition: 'all 0.5s ease-in-out' }} />
            </svg>
        </div>
    );
}