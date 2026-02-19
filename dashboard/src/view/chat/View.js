import { useRef } from "react";
import ViewAPI from './ViewAPI'
export default function View({ }) {

    const {
        messages, onSend, setImage,
        startListening, stopListening, isRecording,
        inputText, setInputText, image
    } = ViewAPI();
    const imageInputRef = useRef(null);
    const audioInputRef = useRef(null);
    const handleSend = () => {
        onSend(inputText);
        if (imageInputRef.current) imageInputRef.current.value = "";
        if (audioInputRef.current) audioInputRef.current.value = "";
    };
    return (
        <div style={{ padding: 20, maxWidth: '80vw', margin: "0 auto" }}>
            <div style={{ height: 300, overflowY: "auto", border: "1px solid #ddd" }}>
                {messages.map(msg => (
                    <div key={msg.id} style={{ textAlign: msg.sender === "user" ? "right" : "left" }}>
                        {msg.image && (
                            <img src={msg.image} alt="" style={{ width: 120, display: "block" }} />
                        )}
                        <p><b>{msg.sender}:</b> {msg.text}</p>
                    </div>
                ))}
            </div>

            {/* 이미지 미리보기 */}
            {image && (
                <div style={{ marginTop: 10 }}>
                    <img
                        src={URL.createObjectURL(image)}
                        alt="preview"
                        style={{ width: 100 }}
                    />
                    <button onClick={() => setImage(null)}>삭제</button>
                </div>
            )}

            {/* 입력창 */}
            <div
                style={{ display: 'flex', marginTop: 10 }}
            >
                <textarea
                    rows={3}
                    value={inputText}
                    onChange={e => setInputText(e.target.value)}
                    placeholder="프롬프트를 입력하세요"
                    style={{ width: "100%" }}
                />

                <button onClick={() => handleSend()}>전송</button>
            </div>

            {/* 하단 컨트롤 */}
            <div style={{ display: "flex", gap: 8, marginTop: 10, backgroundColor: 'skyblue', padding: 10 }}>
                <button
                    onMouseDown={startListening}
                    onMouseUp={stopListening}
                    style={{ background: isRecording ? "red" : "#ccc" }}
                >
                    🎙
                </button>

                <input
                    type="file"
                    accept="image/*"
                    ref={imageInputRef}
                    onChange={e => setImage(e.target.files[0])}
                />

            </div>
        </div>
    );
}