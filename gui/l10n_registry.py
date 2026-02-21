from PyQt6.QtCore import QObject

class L10nMarker(QObject):
    """
    This class is for l10n scanners (pylupdate6) only.
    It contains strings that are used dynamically in the application
    but are coming from JSON definitions (Workflows, Reports, Filters).
    """
    def marker(self):
        # Workflows
        self.tr("Standard Invoice Manager")
        self.tr("Incoming Invoice")
        self.tr("Ready for Payment")
        self.tr("Paid & Archived")
        self.tr("Rejected / Spam")
        self.tr("Verify")
        self.tr("Reject")
        self.tr("Mark as paid")
        self.tr("Reset")
        
        # Reports
        self.tr("Monthly Invoice Count")
        self.tr("Monthly Spending")
        self.tr("Tax Summary YTD")
        self.tr("Tax Overview")
        self.tr("Grand Totals")
        self.tr("Monthly Invoices")
        self.tr("Monthly summary of all invoices.")
        self.tr("Tax Overview (Detailed)")
        
        # Cockpit / Aggregations
        self.tr("Sum")
        self.tr("Avg")
        self.tr("Count")
        self.tr("Min")
        self.tr("Max")
        self.tr("Median")
        self.tr("Percent")
        self.tr("Total Invoiced")
        self.tr("Urgent")
        self.tr("Inbox")
        self.tr("Processed")
        self.tr("Review")
        
        # Standard Filters / Lists
        self.tr("Posteingang")
        self.tr("In Bearbeitung")
        self.tr("Zu Prüfen (AI Flash)")
        self.tr("Amazon Käufe")
        self.tr("Versicherungen & Fixkosten")
        self.tr("Hohe Beträge (> 500€)")
        self.tr("Gesendet (Outbound)")
        self.tr("Aktueller Monat")
        self.tr("Letzte 90 Tage")
        self.tr("Auto-Tax-Tagging")
        self.tr("Standard-Konfiguration")
