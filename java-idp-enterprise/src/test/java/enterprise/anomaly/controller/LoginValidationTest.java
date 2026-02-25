package enterprise.anomaly.controller;

import com.fasterxml.jackson.databind.ObjectMapper;
import enterprise.anomaly.config.AnomalyThresholdConfig;
import enterprise.anomaly.service.MlRiskClient;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import java.util.HashMap;
import java.util.Map;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(DemoController.class)
class LoginValidationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @MockBean
    private MlRiskClient mlRiskClient;

    @MockBean
    private AnomalyThresholdConfig thresholdConfig;

    @Test
    void invalidPayloadReturnsBadRequest() throws Exception {
        Map<String, Object> payload = new HashMap<>();
        payload.put("userId", "");
        payload.put("deviceId", "dev-1");
        payload.put("countryCode", "US");
        payload.put("loginHourNormalized", 1.4);
        payload.put("newDeviceFlag", 2);
        payload.put("countryChangeFlag", 0);
        payload.put("geoDistanceNormalized", 0.2);
        payload.put("ipRiskScore", 0.1);
        payload.put("failedAttemptsLastHour", 0);

        mockMvc.perform(post("/enterprise/login")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(payload)))
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.message").value("Invalid login risk request."));
    }
}
