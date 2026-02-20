package org.agent.service;

import org.springframework.web.multipart.MultipartFile;

import java.util.List;
import java.util.Map;

public interface WebService {
    Map<String, Object> chat(String message);

    Map<String, Object> uploadExcel(MultipartFile file);

    Map<String, Object> learningModel(MultipartFile file, List<String> columns, String category, String target_recommendation, String description, List<String> samples);

    Map<String, Object> getModels();

    Map<String, Object> chatVoiceImage(MultipartFile voiceFile, MultipartFile imageFile, String input);

    Map<String, Object> captureImage(String input, MultipartFile imageFile, String cameraId);
}
