package org.agent.service.weather;

import com.google.gson.JsonParser;
import lombok.extern.slf4j.Slf4j;
import org.springframework.http.HttpEntity;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.ResponseEntity;
import org.springframework.web.client.RestTemplate;
import com.google.gson.JsonObject;
import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Map;

@Slf4j
public class WeatherAlert {
    private static final String govermentKey = "MvdWDyz96xFc2dxh1FEm3x5uvTjgMr9i%2FD2IqwKxMg0nYoS7%2Br1Evs3dR2fpnFSOvqD8JCKl%2FzMu4ucYrZeYMA%3D%3D";
    private static final String kakaoKey = "48326e85016a9a42d0bacba28768fabe";
    private static final String BASE_URL = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst";
    private static final String BASE_CAST_URL = "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtFcst";
    private static final String KAKAOMAP_URL = "https://dapi.kakao.com/v2/local/geo/coord2regioncode";
    private static final double RE = 6371.00877; // 지구 반경(km)
    private static final double GRID = 5.0; // 격자 간격(km)
    private static final double SLAT1 = 30.0; // 표준위도 1
    private static final double SLAT2 = 60.0; // 표준위도 2
    private static final double OLON = 126.0; // 기준점 경도
    private static final double OLAT = 38.0; // 기준점 위도
    private static final double XO = 43; // 기준점 X좌표
    private static final double YO = 136; // 기준점 Y좌표



    public static int[] convertLatLonToGrid(double lat, double lon) {
        double DEGRAD = Math.PI / 180.0;
        double RADDEG = 180.0 / Math.PI;

        double re = RE / GRID;
        double slat1 = SLAT1 * DEGRAD;
        double slat2 = SLAT2 * DEGRAD;
        double olon = OLON * DEGRAD;
        double olat = OLAT * DEGRAD;

        double sn = Math.log(Math.cos(slat1) / Math.cos(slat2)) /
                Math.log(Math.tan(Math.PI * 0.25 + slat2 * 0.5) / Math.tan(Math.PI * 0.25 + slat1 * 0.5));
        double sf = Math.pow(Math.tan(Math.PI * 0.25 + slat1 * 0.5), sn) * Math.cos(slat1) / sn;
        double ro = re * sf / Math.pow(Math.tan(Math.PI * 0.25 + olat * 0.5), sn);

        double ra = re * sf / Math.pow(Math.tan(Math.PI * 0.25 + (lat) * DEGRAD * 0.5), sn);
        double theta = lon * DEGRAD - olon;
        if (theta > Math.PI) theta -= 2.0 * Math.PI;
        if (theta < -Math.PI) theta += 2.0 * Math.PI;
        theta *= sn;

        int nx = (int) Math.floor(ra * Math.sin(theta) + XO + 0.5);
        int ny = (int) Math.floor(ro - ra * Math.cos(theta) + YO + 0.5);

        return new int[]{nx, ny};
    }
    public static String getKakaoMap(String latitude, String longitude){
        String result = "";
        try{

            StringBuilder urlBuilder =  new StringBuilder(KAKAOMAP_URL);
            urlBuilder.append("?" + URLEncoder.encode("x","UTF-8") + "=" +URLEncoder.encode(longitude, "UTF-8"));
            urlBuilder.append("&" + URLEncoder.encode("y","UTF-8") + "=" + URLEncoder.encode(latitude, "UTF-8"));
            URL url = new URL(urlBuilder.toString());

            HttpHeaders headers = new HttpHeaders();
            headers.add("Authorization", "KakaoAK "+ kakaoKey);

            // HttpEntity에 데이터 및 헤더 설정
            HttpEntity<Map<String, String>> requestEntity = new HttpEntity<>(headers);

            // RestTemplate 인스턴스 생성
            RestTemplate restTemplate = new RestTemplate();

            // POST 요청 보내기
            ResponseEntity<String> response = restTemplate.exchange(
                    url.toString(),
                    HttpMethod.GET,
                    requestEntity,
                    String.class
            );
            result = response.getBody();
        } catch (Exception e){
            log.warn("kakao location error : " + e.getMessage());
            return null;
        }
        return result;
    }


    public static JsonObject getWeather(String latitude, String longitude) throws IOException {
        int[] grid = convertLatLonToGrid(Double.parseDouble(latitude), Double.parseDouble(longitude));
        int nx = grid[0];
        int ny = grid[1];
        LocalDateTime today = LocalDateTime.now();
        LocalDateTime dateTime = LocalDateTime.parse(today.toString(), DateTimeFormatter.ISO_DATE_TIME).minusHours(1); //.plusHours(9);

        String baseDate = dateTime.format(DateTimeFormatter.ofPattern("yyyyMMdd"));

        int hour = dateTime.getHour();
        int minute = dateTime.getMinute();
        String baseTime = String.format("%02d", hour) + String.format("%02d", minute);

        StringBuilder urlBuilder = new StringBuilder(BASE_URL);
        urlBuilder.append("?" + URLEncoder.encode("serviceKey","UTF-8") + "=" +govermentKey);
        urlBuilder.append("&" + URLEncoder.encode("pageNo","UTF-8") + "=" + URLEncoder.encode("1", "UTF-8"));
        urlBuilder.append("&" + URLEncoder.encode("numOfRows","UTF-8") + "=" + URLEncoder.encode("8", "UTF-8"));
        urlBuilder.append("&" + URLEncoder.encode("dataType","UTF-8") + "=" + URLEncoder.encode("JSON", "UTF-8"));
        urlBuilder.append("&" + URLEncoder.encode("base_date","UTF-8") + "=" + URLEncoder.encode(baseDate, "UTF-8"));
        urlBuilder.append("&" + URLEncoder.encode("base_time","UTF-8") + "=" + URLEncoder.encode(baseTime, "UTF-8"));
        urlBuilder.append("&" + URLEncoder.encode("nx","UTF-8") + "=" + URLEncoder.encode(String.valueOf(nx), "UTF-8"));
        urlBuilder.append("&" + URLEncoder.encode("ny","UTF-8") + "=" + URLEncoder.encode(String.valueOf(ny), "UTF-8"));
        URL url = new URL(urlBuilder.toString());
//        System.out.println("urlBuilder.toString() : " + urlBuilder.toString());
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod("GET");
        conn.setRequestProperty("Content-type", "application/json");
        BufferedReader rd;
        if(conn.getResponseCode() >= 200 && conn.getResponseCode() <= 300) {
            rd = new BufferedReader(new InputStreamReader(conn.getInputStream()));
        } else {
            rd = new BufferedReader(new InputStreamReader(conn.getErrorStream()));
        }
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = rd.readLine()) != null) {
            sb.append(line);
        }
        rd.close();
        conn.disconnect();
//        System.out.println("sb.toString() : " + sb.toString());
        try {
            return JsonParser.parseString(sb.toString()).getAsJsonObject();
        } catch (Exception e) {
            // API 응답이 JSON 형식이 아닐 경우(에러 발생 시) 예외 처리
            JsonObject errorJson = new JsonObject();
            errorJson.addProperty("error", "JSON_PARSING_FAILED");
            errorJson.addProperty("message", sb.toString());
            return errorJson;
        }
    }
    public static String getWeatherCast(String latitude, String longitude) throws IOException {
        int[] grid = convertLatLonToGrid(Double.parseDouble(latitude), Double.parseDouble(longitude));
        int nx = grid[0];
        int ny = grid[1];
        LocalDateTime today = LocalDateTime.now();
        LocalDateTime now = LocalDateTime.now(); // 한국 시간 기준
//        LocalDateTime dateTime = LocalDateTime.parse(today, DateTimeFormatter.ISO_DATE_TIME).plusHours(9);


        String baseDate = now.format(DateTimeFormatter.ofPattern("yyyyMMdd"));
        String baseTime = now.format(DateTimeFormatter.ofPattern("HH")) + "30"; // 예보는 보통 정각/30분 단위 데이터

//        System.out.println("nx : " + nx + " ny : " + ny);
//        String baseDate = today.format(DateTimeFormatter.ofPattern("yyyyMMdd"));

//        int hour = today.getHour();
//        int minute = today.getMinute();
//        String baseTime = String.format("%02d", hour) + String.format("%02d", minute);

        StringBuilder urlBuilder = new StringBuilder(BASE_CAST_URL);
        urlBuilder.append("?" + URLEncoder.encode("serviceKey","UTF-8") + "=" +govermentKey);
        urlBuilder.append("&" + URLEncoder.encode("pageNo","UTF-8") + "=" + URLEncoder.encode("1", "UTF-8"));
        urlBuilder.append("&" + URLEncoder.encode("numOfRows","UTF-8") + "=" + URLEncoder.encode("48", "UTF-8"));
        urlBuilder.append("&" + URLEncoder.encode("dataType","UTF-8") + "=" + URLEncoder.encode("JSON", "UTF-8"));
        urlBuilder.append("&" + URLEncoder.encode("base_date","UTF-8") + "=" + URLEncoder.encode(baseDate, "UTF-8"));
        urlBuilder.append("&" + URLEncoder.encode("base_time","UTF-8") + "=" + URLEncoder.encode(baseTime, "UTF-8"));
        urlBuilder.append("&" + URLEncoder.encode("nx","UTF-8") + "=" + URLEncoder.encode(String.valueOf(nx), "UTF-8"));
        urlBuilder.append("&" + URLEncoder.encode("ny","UTF-8") + "=" + URLEncoder.encode(String.valueOf(ny), "UTF-8"));
        URL url = new URL(urlBuilder.toString());
//        System.out.println("urlBuilder.toString() : " + urlBuilder.toString());
        HttpURLConnection conn = (HttpURLConnection) url.openConnection();
        conn.setRequestMethod("GET");
        conn.setRequestProperty("Content-type", "application/json");
        BufferedReader rd;
        if(conn.getResponseCode() >= 200 && conn.getResponseCode() <= 300) {
            rd = new BufferedReader(new InputStreamReader(conn.getInputStream()));
        } else {
            rd = new BufferedReader(new InputStreamReader(conn.getErrorStream()));
        }
        StringBuilder sb = new StringBuilder();
        String line;
        while ((line = rd.readLine()) != null) {
            sb.append(line);
        }
        rd.close();
        conn.disconnect();
//        System.out.println("예보 toString() : " + sb.toString());
        return sb.toString();
    }
}


