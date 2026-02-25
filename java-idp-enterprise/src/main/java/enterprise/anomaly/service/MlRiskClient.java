package enterprise.anomaly.service;

import enterprise.anomaly.dto.RiskResponse;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;
import org.springframework.web.client.RestClientException;
import org.springframework.web.client.RestTemplate;

import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.Collections;

@Component
public class MlRiskClient {

    private final RestTemplate restTemplate;
    private final String detectUrl;

    public MlRiskClient(RestTemplate restTemplate,
                        @Value("${anomaly.ml.detect-url:http://ml-risk-engine:9092/detect}") String detectUrl) {
        this.restTemplate = restTemplate;
        this.detectUrl = detectUrl;
    }

    public RiskResponse detect(String userId,
                               List<Double> features,
                               String loginStatus,
                               String countryCode,
                               Integer loginHour,
                               Integer failedAttemptsLastHour,
                               Integer countryChangeFlag,
                               Integer newDeviceFlag,
                               String ipAddress) {
        Map<String, Object> body = new HashMap<>();
        body.put("userId", userId == null ? "anonymous" : userId);
        body.put("features", features);
        body.put("loginStatus", loginStatus == null ? "Success" : loginStatus);
        body.put("countryCode", countryCode == null ? "US" : countryCode);
        body.put("loginHour", loginHour == null ? 12 : loginHour);
        body.put("failedAttemptsLastHour", failedAttemptsLastHour == null ? 0 : failedAttemptsLastHour);
        body.put("countryChangeFlag", countryChangeFlag == null ? 0 : countryChangeFlag);
        body.put("newDeviceFlag", newDeviceFlag == null ? 0 : newDeviceFlag);
        body.put("ipAddress", ipAddress == null ? "" : ipAddress);
        try {
            return restTemplate.postForObject(detectUrl, body, RiskResponse.class);
        } catch (RestClientException ex) {
            return null;
        }
    }

    public List<Map<String, Object>> getUserHistory(String userId, int limit) {
        String base = detectUrl.endsWith("/detect") ? detectUrl.substring(0, detectUrl.length() - "/detect".length()) : detectUrl;
        String historyUrl = base + "/history/{userId}?limit={limit}";
        try {
            Map<?, ?> response = restTemplate.getForObject(historyUrl, Map.class, userId, limit);
            if (response == null || !response.containsKey("points")) {
                return Collections.emptyList();
            }
            Object points = response.get("points");
            if (!(points instanceof List<?> rawList)) {
                return Collections.emptyList();
            }
            return rawList.stream()
                .filter(item -> item instanceof Map<?, ?>)
                .map(item -> (Map<String, Object>) item)
                .toList();
        } catch (RestClientException ex) {
            return Collections.emptyList();
        }
    }

    public List<String> getTrackedUsers(int limit) {
        String base = detectUrl.endsWith("/detect") ? detectUrl.substring(0, detectUrl.length() - "/detect".length()) : detectUrl;
        String usersUrl = base + "/users?limit={limit}";
        try {
            Map<?, ?> response = restTemplate.getForObject(usersUrl, Map.class, limit);
            if (response == null || !response.containsKey("users")) {
                return Collections.emptyList();
            }
            Object users = response.get("users");
            if (!(users instanceof List<?> rawList)) {
                return Collections.emptyList();
            }
            return rawList.stream()
                .filter(item -> item != null)
                .map(String::valueOf)
                .toList();
        } catch (RestClientException ex) {
            return Collections.emptyList();
        }
    }
}
