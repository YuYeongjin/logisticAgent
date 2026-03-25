import { useState, useRef, useEffect, useCallback } from "react";
import AxiosCustom from "../../config/AxiosCustom";
import SpeechRecognition, { useSpeechRecognition } from 'react-speech-recognition';

export default function ViewAPI() {
    const [messages, setMessages] = useState([]);
    const [audio, setAudio] = useState(null);
    const [image, setImage] = useState(null);
    const [isRecording, setIsRecording] = useState(false);
    const [isVoiceMode, setIsVoiceMode] = useState(false);
    const [isSpeaking, setIsSpeaking] = useState(false);

    const isVoiceModeRef = useRef(false);
    const mediaRecorder = useRef(null);
    const audioChunks = useRef([]);

    const [inputText, setInputText] = useState("");
    const { transcript, resetTranscript, listening, browserSupportsSpeechRecognition } = useSpeechRecognition();

    // 일반 모드: transcript가 바뀌면 inputText에 반영
    useEffect(() => {
        if (!isVoiceModeRef.current && transcript) {
            setInputText(prev => (prev || "") + transcript);
        }
    }, [transcript]);

    if (!browserSupportsSpeechRecognition) {
        console.warn("이 브라우저는 음성 인식을 지원하지 않습니다.");
    }

    // TTS: 텍스트를 읽어주고 완료 시 resolve
    const speakText = useCallback((text) => {
        return new Promise((resolve) => {
            window.speechSynthesis.cancel();
            const utterance = new SpeechSynthesisUtterance(text);
            utterance.lang = "ko-KR";
            utterance.rate = 1.0;
            utterance.onend = resolve;
            utterance.onerror = resolve;
            setIsSpeaking(true);
            window.speechSynthesis.speak(utterance);
        }).finally(() => setIsSpeaking(false));
    }, []);

    // 음성 모드에서 한 턴 실행 (듣기 → 전송 → TTS → 다시 듣기)
    const startVoiceListening = useCallback(() => {
        resetTranscript();
        SpeechRecognition.startListening({ continuous: false, language: "ko-KR" });
    }, [resetTranscript]);

    // 음성 모드: listening이 false로 바뀌면 (말이 끝나면) 자동 전송
    useEffect(() => {
        if (!isVoiceModeRef.current) return;
        if (listening) return; // 아직 듣는 중

        const text = transcript.trim();
        if (!text) {
            // 아무 말도 안 했으면 다시 듣기
            if (isVoiceModeRef.current) startVoiceListening();
            return;
        }

        // 자동 전송
        const doSend = async () => {
            const formData = new FormData();
            formData.append("input", text);

            setMessages(prev => [...prev, { id: Date.now(), text, sender: "user" }]);
            resetTranscript();

            try {
                const response = await AxiosCustom.post('/api/sop/chat', formData, {
                    headers: { 'Content-Type': 'multipart/form-data' },
                    withCredentials: true
                });
                const data = typeof response.data === 'string' ? JSON.parse(response.data) : response.data;
                const agentText = data.response;

                setMessages(prev => [...prev, { id: Date.now(), text: agentText, sender: 'agent' }]);

                // TTS로 응답 읽기
                if (isVoiceModeRef.current) {
                    await speakText(agentText);
                }
            } catch (error) {
                console.error("Chat Error:", error);
            }

            // 다시 듣기
            if (isVoiceModeRef.current) startVoiceListening();
        };

        doSend();
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [listening]);

    // 음성 모드 토글
    const toggleVoiceMode = () => {
        const next = !isVoiceMode;
        setIsVoiceMode(next);
        isVoiceModeRef.current = next;

        if (next) {
            window.speechSynthesis.cancel();
            startVoiceListening();
        } else {
            SpeechRecognition.stopListening();
            window.speechSynthesis.cancel();
            setIsSpeaking(false);
        }
    };

    // 일반 모드 버튼: 누르는 동안 듣기
    const startListening = () => {
        resetTranscript();
        setIsRecording(true);
        SpeechRecognition.startListening({ continuous: true, language: "ko-KR" });
    };

    const stopListening = () => {
        setIsRecording(false);
        SpeechRecognition.stopListening();
    };

    const onSend = async (text, audioFile = null) => {
        const sendText = inputText || transcript || text;
        const currentImage = image;

        if (!sendText && !audioFile && !image) return;

        const formData = new FormData();
        formData.append("input", sendText);
        if (audioFile) formData.append("voice_file", audioFile, "user_voice.wav");
        if (currentImage) formData.append("image_file", currentImage);

        setMessages(prev => [...prev, {
            id: Date.now(),
            text: inputText,
            image: image ? URL.createObjectURL(image) : null,
            sender: "user"
        }]);

        try {
            const response = await AxiosCustom.post('/api/sop/chat', formData, {
                headers: { 'Content-Type': 'multipart/form-data' },
                withCredentials: true
            });
            setAudio(null);
            setImage(null);
            setInputText("");
            resetTranscript();

            const data = typeof response.data === 'string' ? JSON.parse(response.data) : response.data;
            setMessages(prev => [...prev, { id: Date.now(), text: data.response, sender: 'agent' }]);
        } catch (error) {
            console.error("Chat Error:", error);
        }
    };

    return {
        messages,
        onSend,
        setMessages,
        setAudio,
        setImage, image,
        startListening, stopListening, isRecording, transcript,
        inputText, setInputText,
        isVoiceMode, toggleVoiceMode, isSpeaking, listening
    };
}