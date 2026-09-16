@auth
Feature: Login

  # Trace(Jira:PROJ-101)
  @smoke
  Scenario: Login with valid credentials
    Given I am on the login page
    When I enter valid credentials
    Then I should see the dashboard

  Scenario: Login with an invalid password
    Given I am on the login page
    When I enter an invalid password
    Then I should see an error message

  @regression
  Scenario Outline: Login as different roles
    Given I am on the login page
    When I log in as a "<role>"
    Then I should see the "<role>" dashboard

    @PROJ-108
    Examples:
      | role  |
      | admin |
      | guest |
