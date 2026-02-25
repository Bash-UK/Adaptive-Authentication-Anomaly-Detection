package enterprise.anomaly.config;

import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.stereotype.Component;

@Component
@ConfigurationProperties(prefix = "anomaly.threshold")
public class AnomalyThresholdConfig {

    private double high;
    private double moderate;
    private double newDeviceBoost;
    private double countryChangeBoost;
    private double geoDistanceBoost;
    private double highIpBoost;
    private double mediumIpBoost;
    private double failedAttemptsHighBoost;
    private double failedAttemptsMediumBoost;
    private double oddHourBoost;
    private double lowConfidenceFloor;

    public double getHigh() {
        return high;
    }

    public void setHigh(double high) {
        this.high = high;
    }

    public double getModerate() {
        return moderate;
    }

    public void setModerate(double moderate) {
        this.moderate = moderate;
    }

    public double getNewDeviceBoost() {
        return newDeviceBoost;
    }

    public void setNewDeviceBoost(double newDeviceBoost) {
        this.newDeviceBoost = newDeviceBoost;
    }

    public double getCountryChangeBoost() {
        return countryChangeBoost;
    }

    public void setCountryChangeBoost(double countryChangeBoost) {
        this.countryChangeBoost = countryChangeBoost;
    }

    public double getGeoDistanceBoost() {
        return geoDistanceBoost;
    }

    public void setGeoDistanceBoost(double geoDistanceBoost) {
        this.geoDistanceBoost = geoDistanceBoost;
    }

    public double getHighIpBoost() {
        return highIpBoost;
    }

    public void setHighIpBoost(double highIpBoost) {
        this.highIpBoost = highIpBoost;
    }

    public double getMediumIpBoost() {
        return mediumIpBoost;
    }

    public void setMediumIpBoost(double mediumIpBoost) {
        this.mediumIpBoost = mediumIpBoost;
    }

    public double getFailedAttemptsHighBoost() {
        return failedAttemptsHighBoost;
    }

    public void setFailedAttemptsHighBoost(double failedAttemptsHighBoost) {
        this.failedAttemptsHighBoost = failedAttemptsHighBoost;
    }

    public double getFailedAttemptsMediumBoost() {
        return failedAttemptsMediumBoost;
    }

    public void setFailedAttemptsMediumBoost(double failedAttemptsMediumBoost) {
        this.failedAttemptsMediumBoost = failedAttemptsMediumBoost;
    }

    public double getOddHourBoost() {
        return oddHourBoost;
    }

    public void setOddHourBoost(double oddHourBoost) {
        this.oddHourBoost = oddHourBoost;
    }

    public double getLowConfidenceFloor() {
        return lowConfidenceFloor;
    }

    public void setLowConfidenceFloor(double lowConfidenceFloor) {
        this.lowConfidenceFloor = lowConfidenceFloor;
    }
}
