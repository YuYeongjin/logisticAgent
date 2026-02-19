package org.agent.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import org.agent.service.WebService;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.multipart.MultipartFile;

import java.util.List;
import java.util.Map;

@RestController
@RequestMapping("/api")
@CrossOrigin(origins = "http://localhost:3000")
public class WebController {

    WebService webService;

    public WebController(WebService webService) {
        this.webService = webService;
    }

//    @PostMapping("/chat")
//    public ResponseEntity<?> handleChat(@RequestBody Map<String, Object> request) {
//
//        String userMessage = request.get("message").toString();
//
//        Map<String,Object> response = webService.chat(userMessage);
//
//        return ResponseEntity.ok(response);
//    }
    @PostMapping("/chat")
    public ResponseEntity<?> chat(
            @RequestPart(value="input", required = false) String input,
            @RequestPart(value = "voice_file", required = false) MultipartFile voiceFile,
            @RequestPart(value= "image_file", required = false) MultipartFile imageFile) {
        return ResponseEntity.ok(webService.chatVoiceImage(voiceFile, imageFile, input));
    }


    @PostMapping("/upload")
    public ResponseEntity<?> handleUpload(@RequestParam("file") MultipartFile file) {
        return ResponseEntity.ok(webService.uploadExcel(file));
    }

    @PostMapping("/learning")
    public ResponseEntity<?> handleLearning(
            @RequestParam("file") MultipartFile file,
            @RequestParam("column") List<String> columnsJson,
            @RequestParam("category") String category,
            @RequestParam("target_recommendation") String target_recommendation,
            @RequestParam("description") String description,
            @RequestParam("samples") List<String> samples
            ) {
        return ResponseEntity.ok(webService.learningModel(file,columnsJson,category, target_recommendation,description,samples));
    }

    @PostMapping("/getModels")
    public ResponseEntity<?> handleGetModels() {
        return ResponseEntity.ok(webService.getModels());
    }
}
