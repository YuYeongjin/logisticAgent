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
import java.time.Duration;
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
