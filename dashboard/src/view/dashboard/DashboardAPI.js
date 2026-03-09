import { useState, useRef, useEffect, useCallback } from "react";
import SockJS from "sockjs-client";
import { Client } from "@stomp/stompjs";
import AxiosCustom from "../../config/AxiosCustom";
import SpeechRecognition, { useSpeechRecognition } from 'react-speech-recognition';
import axios from "axios";

export default function DashboardAPI() {
    const [messages, setMessages] = useState([]);
    const [audio, setAudio] = useState(null);
    const [image, setImage] = useState(null);
    const [isRecording, setIsRecording] = useState(false);

    const [inputText, setInputText] = useState();
    const { transcript, resetTranscript, browserSupportsSpeechRecognition } = useSpeechRecognition();

    const clientRef = useRef(null);
    const [data, setData] = useState([]);
    const [latest, setLatest] = useState();
    const SOCKET_HTTP_URL = "http://192.168.10.20:6060/ws/sensor";
    const [logData, setLogData] = useState([]);
    const [imageList, setImageList] = useState([]);
    const [currentDate, setCurrentDate] = useState(new Date().toLocaleDateString());
    const [currentTime, setCurrentTime] = useState(new Date().toLocaleTimeString());

    //온습도
    const [tempMin, setTempMin] = useState(0)
    const [tempMax, setTempMax] = useState(60)

    const [humMin, setHumMin] = useState(20)
    const [humMax, setHumMax] = useState(80)


    const [isTempAlarm, setIsTempAlarm] = useState(false)
    const [isHumAlarm, setIsHumAlarm] = useState(false)

    useEffect(() => {
        const timer = setInterval(() => {
            setCurrentDate(new Date().toLocaleDateString());
            setCurrentTime(new Date().toLocaleTimeString());
        }, 1000);
        return () => clearInterval(timer);
    }, []);
    // socket connect
    useEffect(() => {
        const client = new Client({
            webSocketFactory: () => new SockJS(SOCKET_HTTP_URL),
            reconnectDelay: 3000, // 자동 재연결
            onConnect: (frame) => {
                // console.log("STOMP Connected:", frame);

                client.subscribe("/topic/sensor", (msg) => {
                    // console.log("Received:", msg.body);
                    try {
                        const data = JSON.parse(msg.body);
                        setLatest(data);
                        setData((prev) => [...prev, data]);
                    } catch {
                        setLatest(msg.body);
                        setData((prev) => [...prev, msg.body]);
                    }
                });

                client.subscribe("/topic/logs", (msg) => {
                    console.log("Received:", msg.body);
                    setLogData(prev => [JSON.parse(msg.body), ...prev]);
                });
            },
            onDisconnect: () => {
                console.log("STOMP Disconnected");
            },
            onStompError: (frame) => {
                console.error("STOMP Error:", frame.headers["message"], frame.body);
            },
            onWebSocketClose: (evt) => {
                console.warn("WebSocket Closed:", evt);
            },
            onWebSocketError: (evt) => {
                console.error("WebSocket Error:", evt);
            },
        });

        client.activate();
        clientRef.current = client;

        return () => {
            client.deactivate();
            clientRef.current = null;
        };
    }, []);


    const [envData, setEnvData] = useState([]);
    useEffect(() => {
        if (!latest || !latest.temperature) return;

        const time = new Date(latest.timestamp)
            .toLocaleTimeString([], {
                hour12: false,
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit'
            });

        const newPoint = {
            time,
            temperature: latest.temperature,
            humidity: latest.humidity,
        };

        setEnvData(prev => {
            const next = [...prev, newPoint];
            return next.length > 30 ? next.slice(-30) : next;
        });
    }, [latest]);

    useEffect(() => {
        AxiosCustom.post('/api/get/temperature', {
            location: 'bridgeA'
        })
            .then((response) => {
                const data = response.data.result
                if (data) {
                    setTempMin(data.min_temperature)
                    setTempMax(data.max_temperature)
                }
            })
        AxiosCustom.post('/api/get/humidity', {
            location: 'bridgeA'
        })
            .then((response) => {
                const data = response.data.result
                if (data) {
                    setHumMin(data.min_humidity)
                    setHumMax(data.max_humidity)
                }
            })
    }, [])
    // 온습도 알림 조정
    useEffect(() => {

        if (!latest) return

        const temp = latest.temperature
        const hum = latest.humidity

        AxiosCustom.post('/api/update/sensor', {
            location: 'bridgeA',
            tempMin: tempMin,
            tempMax: tempMax,
            humMin: humMin,
            humMax: humMax,
        })

        if (temp < tempMin || temp > tempMax) {
            setIsTempAlarm(true)
        } else {
            setIsTempAlarm(false)
        }

        if (hum < humMin || hum > humMax) {
            setIsHumAlarm(true)
        } else {
            setIsHumAlarm(false)
        }

    }, [tempMin, tempMax, humMin, humMax])


    useEffect(() => {
        if (transcript) {
            setInputText(prev => prev + transcript);
        }
    }, [transcript]);

    if (!browserSupportsSpeechRecognition) {
        console.warn("이 브라우저는 음성 인식을 지원하지 않습니다.");
    }

    const startListening = () => {
        resetTranscript();
        setIsRecording(true);
        SpeechRecognition.startListening({
            continuous: true,
            language: "ko-KR"
        });
    };

    const stopListening = () => {
        setIsRecording(false);
        SpeechRecognition.stopListening();
    };
    const onSend = async (text, audioFile = null) => {
        const sendText = inputText || transcript || text;
        const currentImage = image;
        console.log(sendText)
        console.log(image)

        if (!sendText && !audioFile && !image) return;

        const formData = new FormData();
        formData.append("input", sendText);
        if (audioFile) {
            formData.append("voice_file", audioFile, "user_voice.wav");
        }
        if (currentImage) {
            formData.append("image_file", currentImage);
        }
        const myMsg = {
            id: Date.now(),
            text: inputText,
            image: image ? URL.createObjectURL(image) : null,
            sender: "user"
        };
        setMessages(prev => [...prev, myMsg]);
        try {
            const response = await AxiosCustom.post('/api/chat', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
                withCredentials: true
            });
            setAudio(null);
            setImage(null);
            setInputText("");
            resetTranscript();

            const data = typeof response.data === 'string' ? JSON.parse(response.data) : response.data;
            setMessages(prev => [...prev, {
                id: Date.now(),
                text: data.response,
                sender: 'agent'
            }]);
        } catch (error) {
            console.error("Chat Error:", error);
        }
    };


    const [captureInterval, setCaptureInterval] = useState(60); // 기본 60초 주기
    const [isAutoCapturing, setIsAutoCapturing] = useState(false);

    const videoRef = useRef(null); // 카메라 스트림 연결용
    const timerRef = useRef(null); // 타이머 클리어용

    const getCameraStream = async () => {
        try {
            const stream = await navigator.mediaDevices.getUserMedia({
                video: { width: 1280, height: 720 }
            });
            return stream;
        } catch (err) {
            console.error("카메라 연결 실패:", err);
            return null;
        }
    };
    // 🖼️ 2. 특정 비디오 엘리먼트를 캡처하여 서버로 전송 (카메라 ID 추가)
    const captureAndSend = useCallback(async (cameraId, videoElement) => {
        if (!videoElement || videoElement.readyState < 2) return;

        const canvas = document.createElement("canvas");
        canvas.width = videoElement.videoWidth;
        canvas.height = videoElement.videoHeight;
        const ctx = canvas.getContext("2d");
        ctx.drawImage(videoElement, 0, 0);

        canvas.toBlob(async (blob) => {
            if (!blob) return;

            const formData = new FormData();
            // 카메라 ID를 포함하여 서버가 어떤 카메라의 이미지인지 알 수 있게 함
            formData.append("input", `${cameraId}번 카메라 자동 분석`);
            // 파일명에 카메라 ID 명시
            formData.append("image_file", blob, `cam_${cameraId}_${Date.now()}.jpg`);
            formData.append("camera_id", cameraId);

            try {
                console.log("image capture")
                const response = await AxiosCustom.post(
                    // '/api/capture/image'
                    '/api/sop/chat'
                    , formData, {
                    headers: { 'Content-Type': 'multipart/form-data' }
                });

                const data = typeof response.data === 'string' ? JSON.parse(response.data) : response.data;

                setMessages(prev => [...prev, {
                    id: Date.now(),
                    text: `[CAM ${cameraId} 분석]: ${data.response}`,
                    sender: 'agent'
                }]);
            } catch (error) {
                console.error(`${cameraId}번 카메라 전송 에러:`, error);
            }
        }, "image/jpeg", 0.8);
    }, []);

    // ⏱️ 3. 타이머 제어 (설정된 주기에 따라 실행)
    useEffect(() => {
        if (isAutoCapturing) {
            timerRef.current = setInterval(() => {
                captureAndSend();
            }, captureInterval * 1000);
        } else {
            if (timerRef.current) clearInterval(timerRef.current);
        }

        return () => {
            if (timerRef.current) clearInterval(timerRef.current);
        };
    }, [isAutoCapturing, captureInterval, captureAndSend]);

    async function getImage() {
        try {
            const response = await AxiosCustom.post('/api/capture/getOneDay', {
                currentDate: currentDate
            });

            const data = typeof response.data === 'string' ? JSON.parse(response.data) : response.data;
            setImageList(data.result)
            console.log(data.result);
        } catch (error) {
            console.error(error);
        }
    }


    const cameras = [
        { id: 1, name: "1번 작업", status: "NORMAL", color: "#4caf50", isLocal: false, url: "https://via.placeholder.com/300x180/1a1a1a/ffffff?text=CAM+01" },
        { id: 2, name: "2번 작업", status: "NOTICE", color: "#ff9800", isLocal: false, url: "https://via.placeholder.com/300x180/1a1a1a/ffffff?text=CAM+02" },
        { id: 3, name: "3번 작업", status: "WARNING", color: "#f44336", isLocal: true }
    ];
    const videoRefs = useRef({});
    // 이미지 캡처
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
                        getImage();
                    }
                });
            }, captureInterval * 1000);
        }
        return () => clearInterval(intervalId);
    }, [isAutoCapturing, captureInterval, captureAndSend]);
    return {
        messages,
        onSend,
        setMessages,
        setAudio,
        setImage, image,
        startListening, stopListening, isRecording, transcript,
        inputText, setInputText,
        videoRef,
        getCameraStream,
        isAutoCapturing,
        setIsAutoCapturing,
        captureInterval,
        setCaptureInterval,
        sensorData: data,
        latestSensor: latest,
        envData,
        captureAndSend,
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
    };
}