package enterprise.anomaly.controller;

import jakarta.validation.Valid;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

import enterprise.anomaly.config.AnomalyThresholdConfig;
import enterprise.anomaly.dto.AdaptiveAuthResponse;
import enterprise.anomaly.dto.LoginRiskRequest;
import enterprise.anomaly.dto.RiskResponse;
import enterprise.anomaly.service.MlRiskClient;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ConcurrentHashMap;

@RestController
@RequestMapping("/enterprise")
public class DemoController {

    private static final Logger log = LoggerFactory.getLogger(DemoController.class);

    private final AnomalyThresholdConfig thresholdConfig;
    private final MlRiskClient mlRiskClient;
    private final Map<String, String> mfaWarmupFingerprints = new ConcurrentHashMap<>();
    private final String appVersion;

    public DemoController(AnomalyThresholdConfig thresholdConfig,
                          MlRiskClient mlRiskClient,
                          @Value("${app.version:2.0.0}") String appVersion) {
        this.thresholdConfig = thresholdConfig;
        this.mlRiskClient = mlRiskClient;
        this.appVersion = appVersion;
    }

    @PostMapping("/login")
    public AdaptiveAuthResponse simulate(@Valid @RequestBody LoginRiskRequest dto) {
        List<Double> features = Arrays.asList(
            dto.getLoginHourNormalized(),
            (double) dto.getNewDeviceFlag(),
            (double) dto.getCountryChangeFlag(),
            dto.getGeoDistanceNormalized(),
            dto.getIpRiskScore()
        );
        Integer loginHour = dto.getLoginHour();
        if (loginHour == null) {
            loginHour = (int) Math.round(dto.getLoginHourNormalized() * 23.0);
        }

        RiskResponse response = mlRiskClient.detect(dto.getUserId(), features, dto.getLoginStatus(), dto.getCountryCode(), loginHour,
            dto.getFailedAttemptsLastHour(), dto.getCountryChangeFlag(), dto.getNewDeviceFlag(), dto.getIpAddress());
        AdaptiveAuthResponse authResponse = new AdaptiveAuthResponse();

        if (response == null) {
            authResponse.setAction("MFA_CHALLENGE");
            authResponse.setMessage("ML service did not respond, fallback MFA challenge required.");
            authResponse.setFinalRisk(0.50);
            authResponse.setModelRisk(0.50);
            authResponse.setConfidence(0.0);
            authResponse.setReasons(Arrays.asList("ml_service_unavailable"));
            return authResponse;
        }

        double modelRisk = clamp(response.getRisk());
        double finalRisk = modelRisk;
        List<String> reasons = new ArrayList<>();

        if (dto.getNewDeviceFlag() == 1) {
            finalRisk += thresholdConfig.getNewDeviceBoost();
            reasons.add("new_device");
        }
        if (dto.getCountryChangeFlag() == 1) {
            finalRisk += thresholdConfig.getCountryChangeBoost();
            reasons.add("country_changed");
        }
        if (dto.getGeoDistanceNormalized() >= 0.70) {
            finalRisk += thresholdConfig.getGeoDistanceBoost();
            reasons.add("long_geo_distance");
        }
        if (dto.getIpRiskScore() >= 0.70) {
            finalRisk += thresholdConfig.getHighIpBoost();
            reasons.add("high_risk_ip");
        } else if (dto.getIpRiskScore() >= 0.40) {
            finalRisk += thresholdConfig.getMediumIpBoost();
            reasons.add("medium_risk_ip");
        }
        if (dto.getFailedAttemptsLastHour() >= 5) {
            finalRisk += thresholdConfig.getFailedAttemptsHighBoost();
            reasons.add("failed_attempt_spike");
        } else if (dto.getFailedAttemptsLastHour() >= 3) {
            finalRisk += thresholdConfig.getFailedAttemptsMediumBoost();
            reasons.add("elevated_failed_attempts");
        }
        if (dto.getLoginHourNormalized() <= 0.20 || dto.getLoginHourNormalized() >= 0.90) {
            finalRisk += thresholdConfig.getOddHourBoost();
            reasons.add("odd_login_hour");
        }

        finalRisk = clamp(finalRisk);

        String action;
        if (finalRisk >= thresholdConfig.getHigh()) {
            action = "BLOCK";
        } else if (finalRisk >= thresholdConfig.getModerate()) {
            action = "MFA_CHALLENGE";
        } else {
            action = "ALLOW";
        }

        double confidence = response.getConfidence();
        if (confidence < thresholdConfig.getLowConfidenceFloor() && "ALLOW".equals(action)) {
            action = "MFA_CHALLENGE";
            reasons.add("low_model_confidence");
        }

        // Warm-up trust rule:
        // 1) First low-confidence MFA stores a behavior fingerprint.
        // 2) If next login has same fingerprint and no elevated-risk reasons, auto-allow.
        String userId = dto.getUserId();
        String fingerprint = behaviorFingerprint(dto);
        boolean onlyLowConfidence = reasons.size() == 1 && reasons.contains("low_model_confidence");
        if ("MFA_CHALLENGE".equals(action) && onlyLowConfidence) {
            String known = mfaWarmupFingerprints.get(userId);
            if (fingerprint.equals(known)) {
                action = "ALLOW";
                reasons.clear();
                reasons.add("warmup_profile_match");
            } else {
                mfaWarmupFingerprints.put(userId, fingerprint);
                reasons.add("warmup_first_seen");
            }
        }

        authResponse.setAction(action);
        authResponse.setFinalRisk(finalRisk);
        authResponse.setModelRisk(modelRisk);
        authResponse.setConfidence(confidence);
        authResponse.setReasons(reasons);
        authResponse.setMessage("Adaptive authentication policy evaluated successfully.");
        log.info("anomaly_decision userId={} action={} finalRisk={} modelRisk={} reasons={}",
            dto.getUserId(), action, finalRisk, modelRisk, reasons);
        return authResponse;
    }

    @GetMapping("/user/{userId}/history")
    public Map<String, Object> userHistory(@PathVariable("userId") String userId,
                                           @RequestParam(name = "limit", defaultValue = "60") int limit) {
        int safeLimit = Math.max(1, Math.min(500, limit));
        List<Map<String, Object>> points = mlRiskClient.getUserHistory(userId, safeLimit);
        Map<String, Object> out = new HashMap<>();
        out.put("userId", userId);
        out.put("points", points);
        return out;
    }

    @GetMapping("/users")
    public Map<String, Object> users(@RequestParam(name = "limit", defaultValue = "200") int limit) {
        int safeLimit = Math.max(1, Math.min(1000, limit));
        List<String> users = mlRiskClient.getTrackedUsers(safeLimit);
        Map<String, Object> out = new HashMap<>();
        out.put("users", users);
        return out;
    }

    @GetMapping("/version")
    public Map<String, Object> version() {
        Map<String, Object> out = new HashMap<>();
        out.put("service", "idp-backend");
        out.put("version", appVersion);
        return out;
    }

    private double clamp(double value) {
        if (value < 0.0) {
            return 0.0;
        }
        if (value > 1.0) {
            return 1.0;
        }
        return value;
    }

    private String behaviorFingerprint(LoginRiskRequest dto) {
        int hourBucket = (int) Math.round(dto.getLoginHourNormalized() * 24.0);
        int ipBucket = (int) Math.floor(dto.getIpRiskScore() * 10.0);
        return String.join("|",
            safe(dto.getDeviceId()),
            safe(dto.getCountryCode()).toUpperCase(),
            safe(dto.getLoginStatus()).toLowerCase(),
            String.valueOf(dto.getNewDeviceFlag()),
            String.valueOf(dto.getCountryChangeFlag()),
            String.valueOf(dto.getFailedAttemptsLastHour()),
            String.valueOf(hourBucket),
            String.valueOf(ipBucket)
        );
    }

    private String safe(String value) {
        return value == null ? "" : value.trim();
    }
}
