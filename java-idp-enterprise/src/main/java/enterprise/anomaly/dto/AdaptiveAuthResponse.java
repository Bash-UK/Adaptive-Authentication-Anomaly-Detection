package enterprise.anomaly.dto;

import java.util.List;

public class AdaptiveAuthResponse {

    private String action;
    private double finalRisk;
    private double modelRisk;
    private double confidence;
    private List<String> reasons;
    private String message;

    public String getAction() {
        return action;
    }

    public void setAction(String action) {
        this.action = action;
    }

    public double getFinalRisk() {
        return finalRisk;
    }

    public void setFinalRisk(double finalRisk) {
        this.finalRisk = finalRisk;
    }

    public double getModelRisk() {
        return modelRisk;
    }

    public void setModelRisk(double modelRisk) {
        this.modelRisk = modelRisk;
    }

    public double getConfidence() {
        return confidence;
    }

    public void setConfidence(double confidence) {
        this.confidence = confidence;
    }

    public List<String> getReasons() {
        return reasons;
    }

    public void setReasons(List<String> reasons) {
        this.reasons = reasons;
    }

    public String getMessage() {
        return message;
    }

    public void setMessage(String message) {
        this.message = message;
    }
}
