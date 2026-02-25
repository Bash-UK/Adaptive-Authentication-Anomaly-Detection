package enterprise.anomaly.controller;

import enterprise.anomaly.config.AnomalyThresholdConfig;
import enterprise.anomaly.dto.AdaptiveAuthResponse;
import enterprise.anomaly.dto.LoginRiskRequest;
import enterprise.anomaly.dto.RiskResponse;
import enterprise.anomaly.service.MlRiskClient;
import org.junit.jupiter.api.Test;
import org.mockito.Mockito;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

class DemoControllerTest {

    @Test
    void fallbackWhenMlServiceUnavailable() {
        MlRiskClient mlRiskClient = Mockito.mock(MlRiskClient.class);
        Mockito.when(mlRiskClient.detect(
            Mockito.any(),
            Mockito.anyList(),
            Mockito.any(),
            Mockito.any(),
            Mockito.any(),
            Mockito.any(),
            Mockito.any(),
            Mockito.any(),
            Mockito.any()
        )).thenReturn(null);
        DemoController controller = new DemoController(thresholds(), mlRiskClient, "2.0.0");

        AdaptiveAuthResponse response = controller.simulate(validRequest());

        assertEquals("MFA_CHALLENGE", response.getAction());
        assertTrue(response.getReasons().contains("ml_service_unavailable"));
    }

    @Test
    void blockWhenFinalRiskCrossesHighThreshold() {
        MlRiskClient mlRiskClient = Mockito.mock(MlRiskClient.class);
        RiskResponse risk = new RiskResponse();
        risk.setRisk(0.72);
        risk.setConfidence(0.88);
        Mockito.when(mlRiskClient.detect(
            Mockito.any(),
            Mockito.anyList(),
            Mockito.any(),
            Mockito.any(),
            Mockito.any(),
            Mockito.any(),
            Mockito.any(),
            Mockito.any(),
            Mockito.any()
        )).thenReturn(risk);
        DemoController controller = new DemoController(thresholds(), mlRiskClient, "2.0.0");

        LoginRiskRequest request = validRequest();
        request.setNewDeviceFlag(1);
        request.setCountryChangeFlag(1);
        request.setGeoDistanceNormalized(0.8);
        request.setIpRiskScore(0.81);
        request.setFailedAttemptsLastHour(6);
        request.setLoginHourNormalized(0.95);

        AdaptiveAuthResponse response = controller.simulate(request);

        assertEquals("BLOCK", response.getAction());
        assertTrue(response.getFinalRisk() >= 0.75);
    }

    @Test
    void lowConfidenceAllowIsEscalatedToMfa() {
        MlRiskClient mlRiskClient = Mockito.mock(MlRiskClient.class);
        RiskResponse risk = new RiskResponse();
        risk.setRisk(0.20);
        risk.setConfidence(0.55);
        Mockito.when(mlRiskClient.detect(
            Mockito.any(),
            Mockito.anyList(),
            Mockito.any(),
            Mockito.any(),
            Mockito.any(),
            Mockito.any(),
            Mockito.any(),
            Mockito.any(),
            Mockito.any()
        )).thenReturn(risk);
        DemoController controller = new DemoController(thresholds(), mlRiskClient, "2.0.0");

        AdaptiveAuthResponse response = controller.simulate(validRequest());

        assertEquals("MFA_CHALLENGE", response.getAction());
        assertTrue(response.getReasons().contains("low_model_confidence"));
    }

    private static LoginRiskRequest validRequest() {
        LoginRiskRequest req = new LoginRiskRequest();
        req.setUserId("u-1001");
        req.setDeviceId("dev-001");
        req.setCountryCode("US");
        req.setLoginHourNormalized(0.40);
        req.setNewDeviceFlag(0);
        req.setCountryChangeFlag(0);
        req.setGeoDistanceNormalized(0.10);
        req.setIpRiskScore(0.15);
        req.setFailedAttemptsLastHour(0);
        return req;
    }

    private static AnomalyThresholdConfig thresholds() {
        AnomalyThresholdConfig cfg = new AnomalyThresholdConfig();
        cfg.setHigh(0.75);
        cfg.setModerate(0.45);
        cfg.setNewDeviceBoost(0.12);
        cfg.setCountryChangeBoost(0.10);
        cfg.setGeoDistanceBoost(0.08);
        cfg.setHighIpBoost(0.12);
        cfg.setMediumIpBoost(0.06);
        cfg.setFailedAttemptsHighBoost(0.15);
        cfg.setFailedAttemptsMediumBoost(0.08);
        cfg.setOddHourBoost(0.04);
        cfg.setLowConfidenceFloor(0.65);
        return cfg;
    }
}
