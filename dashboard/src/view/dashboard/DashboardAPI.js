import { useState, useRef, useEffect } from "react";
import AxiosCustom from "../../config/AxiosCustom";
import SpeechRecognition, { useSpeechRecognition } from 'react-speech-recognition';

export default function DashboardAPI() {
    const [messages, setMessages] = useState([]);
    const [audio, setAudio] = useState(null);
    const [image, setImage] = useState(null);
    const [isRecording, setIsRecording] = useState(false);

    const mediaRecorder = useRef(null);
    const audioChunks = useRef([]);

    const [inputText, setInputText] = useState();
    const { transcript, resetTranscript, browserSupportsSpeechRecognition } = useSpeechRecognition();


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
                headers: { 'Content-Type': 'multipart/form-data' }
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

    return {
        messages,
        onSend,
        setMessages,
        setAudio,
        setImage,image,
        startListening, stopListening, isRecording, transcript,
        inputText, setInputText
    };
}