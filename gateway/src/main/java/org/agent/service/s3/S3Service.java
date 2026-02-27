package org.agent.service.s3;

import lombok.RequiredArgsConstructor;
import lombok.extern.slf4j.Slf4j;
import org.springframework.stereotype.Service;
import software.amazon.awssdk.core.sync.RequestBody;
import software.amazon.awssdk.services.s3.S3Client;
import software.amazon.awssdk.services.s3.model.*;
import software.amazon.awssdk.services.s3.paginators.ListObjectsV2Iterable;
import software.amazon.awssdk.services.s3.presigner.S3Presigner;
import software.amazon.awssdk.services.s3.presigner.model.*;

import java.io.InputStream;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Map;

@Slf4j
@RequiredArgsConstructor
@Service
public class S3Service {

    private final S3Client s3Client;
    private final S3Presigner s3Presigner;


    // 업로드 (InputStream 업로드, 아직 미개발)
    public String upload(String bucket, String key, InputStream in, String contentType, long contentLength) {
        PutObjectRequest put = PutObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .contentType(contentType)
                .build();

        s3Client.putObject(put, RequestBody.fromInputStream(in, contentLength));
        return key;
    }

    public String createPresignedPutUrl(String bucket, String key, Duration ttl) {
        PutObjectRequest put = PutObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .build();

        PresignedPutObjectRequest pre = s3Presigner.presignPutObject(
                PutObjectPresignRequest.builder()
                        .signatureDuration(ttl)
                        .putObjectRequest(put)
                        .build()
        );
        return pre.url().toString();
    }

    public String createPresignedGetUrl(String bucket, String key, Duration ttl) {
        GetObjectRequest get = GetObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .responseContentDisposition("inline").build();

        PresignedGetObjectRequest pre = s3Presigner.presignGetObject(
                GetObjectPresignRequest.builder()
                        .signatureDuration(ttl)
                        .getObjectRequest(get).build()
        );
        return pre.url().toString();
    }

    public String createPresignedDeleteUrl(String bucket, String key, Duration ttl) {
        DeleteObjectRequest deleteReq = DeleteObjectRequest.builder()
                .bucket(bucket)
                .key(key)
                .build();

        DeleteObjectPresignRequest presignReq = DeleteObjectPresignRequest.builder()
                .signatureDuration(ttl)
                .deleteObjectRequest(deleteReq)
                .build();

        PresignedDeleteObjectRequest presigned = s3Presigner.presignDeleteObject(presignReq);

        return presigned.url().toString();
    }

    // 리턴 타입 변경: List<String> -> List<Map<String, String>>
    public List<Map<String, String>> createPresignedGetAllUrl(String bucket, Duration ttl) {
        List<Map<String, String>> resultList = new ArrayList<>();

        // ... (기존 ListObjectsV2Request 생성 로직 동일) ...
        ListObjectsV2Request listReq = ListObjectsV2Request.builder().bucket(bucket).build();
        ListObjectsV2Iterable listRes = s3Client.listObjectsV2Paginator(listReq);

        for (S3Object content : listRes.contents()) {
            String key = content.key(); // 1. 파일 이름(Key) 확보

            // ... (기존 Presigned URL 생성 로직 동일) ...
            GetObjectRequest getReq = GetObjectRequest.builder().bucket(bucket).key(key).build();
            GetObjectPresignRequest preReq = GetObjectPresignRequest.builder()
                    .signatureDuration(ttl).getObjectRequest(getReq).build();
            String url = s3Presigner.presignGetObject(preReq).url().toString();

            // 2. Map에 이름과 URL을 담아서 리스트에 추가
            Map<String, String> data = new HashMap<>();
            data.put("name", key); // 파일 이름
            data.put("url", url);  // URL

            resultList.add(data);
        }

        return resultList;
    }

    public List<Map<String, String>> getImagesByDate(String bucket, String targetDate, Duration ttl) {
        List<Map<String, String>> resultList = new ArrayList<>();
        DateTimeFormatter formatter = DateTimeFormatter.ofPattern("yyyy. M. d.");

        // 2. 정의된 포맷터로 파싱
        LocalDate date = LocalDate.parse(targetDate, formatter);

        long startTs = date.atStartOfDay(ZoneId.systemDefault()).toInstant().toEpochMilli();
        long endTs = date.plusDays(1).atStartOfDay(ZoneId.systemDefault()).toInstant().toEpochMilli();

        ListObjectsV2Request listReq = ListObjectsV2Request.builder().bucket(bucket).build();
        ListObjectsV2Iterable listRes = s3Client.listObjectsV2Paginator(listReq);

        for (S3Object content : listRes.contents()) {
            String key = content.key();

            try {
                // 2. 파일명에서 타임스탬프 추출 (cam_1_1771837134031.jpg -> 1771837134031)
                String[] parts = key.split("_");
                String tsStr = parts[2].replace(".jpg", "");
                long fileTs = Long.parseLong(tsStr);

                // 3. 해당 날짜 범위에 포함되는지 확인
                if (fileTs >= startTs && fileTs < endTs) {
                    // Presigned URL 생성 로직 (기존과 동일)
                    GetObjectRequest getReq = GetObjectRequest.builder().bucket(bucket).key(key).build();
                    GetObjectPresignRequest preReq = GetObjectPresignRequest.builder()
                            .signatureDuration(ttl).getObjectRequest(getReq).build();
                    String url = s3Presigner.presignGetObject(preReq).url().toString();

                    Map<String, String> data = new HashMap<>();
                    data.put("name", key);
                    data.put("url", url);
                    data.put("time", formatTime(fileTs)); // 읽기 쉬운 시간으로 변환
                    resultList.add(data);
                }
            } catch (Exception e) {
                // 형식에 맞지 않는 파일명은 스킵
            }
        }
        resultList.sort((m1, m2) -> m2.get("name").substring(5,m2.get("name").length()-1).compareTo(m1.get("name").substring(5,m1.get("name").length()-1)));
        return resultList;
    }

    private String formatTime(long timestamp) {
        return LocalDateTime.ofInstant(Instant.ofEpochMilli(timestamp), ZoneId.systemDefault())
                .format(DateTimeFormatter.ofPattern("HH:mm:ss"));
    }
    public void deleteS3ObjectMono(String bucket, String key) {
        try {
            DeleteObjectRequest deleteReq = DeleteObjectRequest.builder()
                    .bucket(bucket)
                    .key(key)
                    .build();

            s3Client.deleteObject(deleteReq);
        } catch (S3Exception e) {
            e.printStackTrace();
        }
    }
}
