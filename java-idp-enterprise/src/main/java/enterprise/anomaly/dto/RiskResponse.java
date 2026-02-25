package enterprise.anomaly.dto;

public class RiskResponse {

    private double risk;
    private double aeError;
    private double aeRiskComponent;
    private double isolationRaw;
    private double isolationRiskComponent;
    private double confidence;

    public double getRisk() {
        return risk;
    }

    public void setRisk(double risk) {
        this.risk = risk;
    }

    public double getAeError() {
        return aeError;
    }

    public void setAeError(double aeError) {
        this.aeError = aeError;
    }

    public double getAeRiskComponent() {
        return aeRiskComponent;
    }

    public void setAeRiskComponent(double aeRiskComponent) {
        this.aeRiskComponent = aeRiskComponent;
    }

    public double getIsolationRaw() {
        return isolationRaw;
    }

    public void setIsolationRaw(double isolationRaw) {
        this.isolationRaw = isolationRaw;
    }

    public double getIsolationRiskComponent() {
        return isolationRiskComponent;
    }

    public void setIsolationRiskComponent(double isolationRiskComponent) {
        this.isolationRiskComponent = isolationRiskComponent;
    }

    public double getConfidence() {
        return confidence;
    }

    public void setConfidence(double confidence) {
        this.confidence = confidence;
    }
}
