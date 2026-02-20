package org.agent.service;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.agent.database.dao.SensorDAO;
import org.agent.service.s3.S3Service;
import org.agent.service.weather.WeatherAlert;
import org.apache.poi.ss.usermodel.*;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.io.FileSystemResource;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Service;
import org.springframework.util.LinkedMultiValueMap;
import org.springframework.util.MultiValueMap;
import org.springframework.web.client.RestTemplate;

import java.io.BufferedReader;
import java.io.File;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.URI;
import java.util.*;

import com.google.gson.JsonObject;
import org.springframework.web.multipart.MultipartFile;

@Slf4j
@Service
@RequiredArgsConstructor
public class WebServiceImpl implements WebService {

    private final S3Service s3Service;
    private final SensorDAO sensorDAO;
    RestTemplate restTemplate = new RestTemplate();
    @Value("${minio.bucket}")
    private String bucketName;

    @Override
    public Map<String, Object> chat(String message) {
        Map<String,Object> request = new HashMap<>();

        JsonObject  object = new JsonObject();
        try {
            object = WeatherAlert.getWeather(String.valueOf(37),String.valueOf(127));
        } catch (IOException e) {
            throw new RuntimeException(e);
        }
        JsonArray array = new JsonArray();
        array = object.getAsJsonObject("response").getAsJsonObject("body").getAsJsonObject("items").getAsJsonArray("item");
        Map<String,String> reqWeather = new HashMap<>();
        for(int i=0;i<array.size();i++){
            JsonElement element = array.get(i);

            reqWeather.put(element.getAsJsonObject().get("category").getAsString(), element.getAsJsonObject().get("obsrValue").getAsString());
        }
        Map<String,Object> weather = new HashMap<>();
        weather.put("T1H", Double.parseDouble(reqWeather.get("T1H")));
        weather.put("RN1", Double.parseDouble(reqWeather.get("RN1")));
        weather.put("PTY", Integer.parseInt(reqWeather.get("PTY")));
        weather.put("REH", Double.parseDouble(reqWeather.get("REH")));
        weather.put("WSD", Double.parseDouble(reqWeather.get("WSD")));
        request.put("input", message);
        request.put("weather", weather);
        Map<String, Object> result = new HashMap<>();
        result = restTemplate.postForObject(URI.create("http://localhost:8003/chat"), request,Map.class);
        result.put("message", message);

        return result;
    }

    @Override
    public Map<String, Object> uploadExcel(MultipartFile req) {
        Map<String, Object> result = new HashMap<>();
        System.out.println("FILE : " + req.getOriginalFilename());
        String fileName = req.getOriginalFilename();
        Map<String,Object> reqLLM = new HashMap<>();

        if (fileName != null && fileName.endsWith(".csv")) {
           return processCsv(req);
        }

        try (Workbook workbook = WorkbookFactory.create(req.getInputStream())) {

            Sheet sheet = workbook.getSheetAt(0);
            Row headerRow = sheet.getRow(0);

            List<String> columns = new ArrayList<>();
            for (Cell cell : headerRow) {
                columns.add(cell.getStringCellValue());
            }

            int rowCount = sheet.getPhysicalNumberOfRows() - 1;

            // 샘플 데이터 (상위 5개)
            List<Map<String, String>> samples = new ArrayList<>();
            for (int i = 1; i <= Math.min(5, rowCount); i++) {
                Row row = sheet.getRow(i);
                Map<String, String> rowData = new HashMap<>();
                for (int j = 0; j < columns.size(); j++) {
                    Cell cell = row.getCell(j);
                    rowData.put(columns.get(j), cell == null ? "" : cell.toString());
                }
                samples.add(rowData);
            }

            result.put("sheetName", sheet.getSheetName());
            result.put("columns", columns);
            result.put("rowCount", rowCount);
            result.put("samples", samples);
            reqLLM.put("columns", columns);
            reqLLM.put("samples", samples);

        } catch (Exception e) {
            throw new RuntimeException("엑셀 분석 실패", e);
        }
        result.put("analyze",restTemplate.postForObject(URI.create("http://localhost:8001/analyze"), reqLLM,Map.class));
        System.out.println("result :: " + result);

        return result;
    }

    @Override
    public Map<String, Object> learningModel(MultipartFile file, List<String> columns, String category, String target_recommendation, String description, List<String> samples) {
        File convFile = new File(System.getProperty("java.io.tmpdir") + "/" + file.getOriginalFilename());
        try {
            file.transferTo(convFile);
        } catch (IOException e) {
            throw new RuntimeException("파일 변환 실패", e);
        }
        Map<String, Object> analyze = new HashMap<>();
        analyze.put("category",category);
        analyze.put("target_recommendation", target_recommendation);
        analyze.put("description", description);

        // 2. 요청 바디 구성 (MultipartForm)
        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("file", new FileSystemResource(convFile));
        body.add("columns", String.join(",", columns)); // 쉼표 구분자로 전달
        body.add("samples", String.join(",", samples)); // 쉼표 구분자로 전달
        body.add("analyze", analyze);
        System.out.println("body :: " + body);
        // 3. 헤더 설정
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);

        HttpEntity<MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, headers);

        // 4. Python 서버 호출
        Map<String, Object> result = restTemplate.postForObject("http://localhost:8001/train", requestEntity, Map.class);


        // 임시 파일 삭제
        convFile.delete();

        return result;
    }

    @Override
    public Map<String, Object> getModels() {
        ResponseEntity<List> response = restTemplate.getForEntity(
                "http://localhost:8001/models",
                List.class
        );

        List<?> models = response.getBody();

        return Map.of(
                "status", "success",
                "result", models
        );
    }

    @Override
    public Map<String, Object> chatVoiceImage(MultipartFile voiceFile, MultipartFile imageFile, String input) {
        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);

        // 2. 바디 구성 (LinkedMultiValueMap 필수)
        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("input", input);

        // 음성 파일 처리
        if (voiceFile != null && !voiceFile.isEmpty()) {
            System.out.println("@@ 음성들어감 @@ ");
            body.add("voice_file", voiceFile.getResource());
        }
        // 이미지 파일 처리
        if (imageFile != null && !imageFile.isEmpty()) {
            System.out.println("@@ 그림들어감 @@ ");
            body.add("image_file", imageFile.getResource());
        }

        // 3. 요청 생성
        HttpEntity<MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, headers);

        // 4. FastAPI 서버 호출
        Map<String, Object> result = restTemplate.postForObject(
                URI.create("http://localhost:8003/chat"),
                requestEntity,
                Map.class
        );

        result.put("message", input);
        System.out.println("result :: " + result);
        return result;
    }

    @Override
    public Map<String, Object> captureImage(String input, MultipartFile imageFile, String cameraId) {

        // minio add
        try {
            s3Service.upload(
                    bucketName,
                    imageFile.getOriginalFilename(),
                    imageFile.getInputStream(),
                    imageFile.getContentType(),
                    imageFile.getSize()
            );
        } catch (IOException e) {
            throw new RuntimeException(e);
        }


        HttpHeaders headers = new HttpHeaders();
        headers.setContentType(MediaType.MULTIPART_FORM_DATA);


        MultiValueMap<String, Object> body = new LinkedMultiValueMap<>();
        body.add("input", input);
        if (imageFile != null && !imageFile.isEmpty()) {
            body.add("image_file", imageFile.getResource());
            body.add("image_name", imageFile.getOriginalFilename());
        }
        HttpEntity<MultiValueMap<String, Object>> requestEntity = new HttpEntity<>(body, headers);

        // 4. FastAPI 서버 호출
        Map<String, Object> result = restTemplate.postForObject(
                URI.create("http://localhost:8003/imageCheck"),
                requestEntity,
                Map.class
        );
        System.out.println("result :: " + result);

        if(result != null){
            switch (result.get("log_level").toString()){
                case "warn":
                case "danger" :
                    sensorDAO.insertLog(result.get("log_level").toString(), Double.parseDouble( result.get("diff_score").toString()),result.get("response").toString(),"imageCheck");
                    break;
            }

        }
        return result;
    }

    private Map<String, Object> processCsv(MultipartFile file) {
        Map<String, Object> result = new HashMap<>();
        Map<String,Object> reqLLM = new HashMap<>();
        // 인코딩을 UTF-8로 강제 지정
        try (BufferedReader br = new BufferedReader(new InputStreamReader(file.getInputStream(), "UTF-8"))) {
            String line;
            List<String> columns = new ArrayList<>();
            List<Map<String, String>> samples = new ArrayList<>();
            int rowCount = 0;

            while ((line = br.readLine()) != null) {
                // 빈 줄 건너뛰기
                if (line.trim().isEmpty()) continue;

                // 1. [핵심] 첫 줄 BOM(Byte Order Mark) 제거
                // 데이터가 "﻿transaction_hash" 처럼 앞에 점이 붙어 나오는 현상 해결
                if (rowCount == 0) {
                    if (line.startsWith("\uFEFF")) {
                        line = line.substring(1);
                    }
                }

                // 2. [핵심] 탭이 아닌 '쉼표'로 쪼개기
                // 현재 데이터가 쉼표로 연결되어 있으므로 반드시 ","여야 함
                String[] values = line.split(",");

                if (rowCount == 0) {
                    // 컬럼명 리스트 생성
                    for (String value : values) {
                        columns.add(value.trim()); // 공백 제거
                    }
                } else if (rowCount <= 5) {
                    // 샘플 데이터 5개 생성
                    Map<String, String> rowData = new HashMap<>();
                    int limit = Math.min(values.length, columns.size());
                    for (int j = 0; j < limit; j++) {
                        rowData.put(columns.get(j), values[j].trim());
                    }
                    samples.add(rowData);
                }
                rowCount++;
            }

            // 최종 결과 매핑
            result.put("columns", columns); // 이제 Array(13) 정도로 나올 겁니다.
            result.put("rowCount", rowCount - 1);
            result.put("samples", samples);
            reqLLM.put("columns", columns);
            reqLLM.put("samples", samples);

            result.put("analyze",restTemplate.postForObject(URI.create("http://localhost:8001/analyze"), reqLLM,Map.class));
            System.out.println("result :: " + result);
        } catch (Exception e) {
            throw new RuntimeException("CSV 파싱 실패: " + e.getMessage(), e);
        }
        return result;
    }
}
