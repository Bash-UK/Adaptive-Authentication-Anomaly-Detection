package enterprise.anomaly.dto;

import jakarta.validation.constraints.DecimalMax;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;

public class LoginRiskRequest {

    @NotBlank
    private String userId;
    @NotBlank
    private String deviceId;
    @NotBlank
    private String countryCode;
    private String loginStatus;
    private String ipAddress;
    @Min(0)
    @Max(23)
    private Integer loginHour;
    @DecimalMin("0.0")
    @DecimalMax("1.0")
    private double loginHourNormalized;
    @Min(0)
    @Max(1)
    private int newDeviceFlag;
    @Min(0)
    @Max(1)
    private int countryChangeFlag;
    @DecimalMin("0.0")
    @DecimalMax("1.0")
    private double geoDistanceNormalized;
    @DecimalMin("0.0")
    @DecimalMax("1.0")
    private double ipRiskScore;
    @Min(0)
    private int failedAttemptsLastHour;

    public String getUserId() { return userId; }
    public void setUserId(String userId) { this.userId = userId; }

    public String getDeviceId() { return deviceId; }
    public void setDeviceId(String deviceId) { this.deviceId = deviceId; }

    public String getCountryCode() { return countryCode; }
    public void setCountryCode(String countryCode) { this.countryCode = countryCode; }

    public String getLoginStatus() { return loginStatus; }
    public void setLoginStatus(String loginStatus) { this.loginStatus = loginStatus; }

    public String getIpAddress() { return ipAddress; }
    public void setIpAddress(String ipAddress) { this.ipAddress = ipAddress; }

    public Integer getLoginHour() { return loginHour; }
    public void setLoginHour(Integer loginHour) { this.loginHour = loginHour; }

    public double getLoginHourNormalized() { return loginHourNormalized; }
    public void setLoginHourNormalized(double v) { this.loginHourNormalized = v; }

    public int getNewDeviceFlag() { return newDeviceFlag; }
    public void setNewDeviceFlag(int v) { this.newDeviceFlag = v; }

    public int getCountryChangeFlag() { return countryChangeFlag; }
    public void setCountryChangeFlag(int v) { this.countryChangeFlag = v; }

    public double getGeoDistanceNormalized() { return geoDistanceNormalized; }
    public void setGeoDistanceNormalized(double v) { this.geoDistanceNormalized = v; }

    public double getIpRiskScore() { return ipRiskScore; }
    public void setIpRiskScore(double v) { this.ipRiskScore = v; }

    public int getFailedAttemptsLastHour() { return failedAttemptsLastHour; }
    public void setFailedAttemptsLastHour(int failedAttemptsLastHour) { this.failedAttemptsLastHour = failedAttemptsLastHour; }
}
