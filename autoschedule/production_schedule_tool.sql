-- Basic Data Overview
-- Count total records and check for NULLs in key fields
IF OBJECT_ID('auto_schedule.vw_BasicDataOverview') IS NOT NULL
    DROP VIEW auto_schedule.vw_BasicDataOverview;
GO
CREATE VIEW auto_schedule.vw_BasicDataOverview AS
SELECT 
    COUNT(*) AS TotalRecords,
    SUM(CASE WHEN PNum IS NULL or PNum in ('', ' ', '  ') THEN 1 ELSE 0 END) AS MissingERPNum,
    SUM(CASE WHEN DeliveryDate IS NULL or DeliveryDate in ('', ' ', '  ') THEN 1 ELSE 0 END) AS MissingDeliveryDate,
    SUM(CASE WHEN Customer IS NULL or Customer in ('', ' ', '  ') THEN 1 ELSE 0 END) AS MissingCustomer
FROM VW_QueDGNBDetail;
GO
-- 24349	2362	264	0


-- 1. Delivery Analysis
-- Rank by Delivery Date and identify urgent and missed deadlines
IF OBJECT_ID('auto_schedule.vw_DeliveryAnalysis') IS NOT NULL
    DROP VIEW auto_schedule.vw_DeliveryAnalysis;
GO
CREATE VIEW auto_schedule.vw_DeliveryAnalysis AS
SELECT 
    PNum,
    Customer,
    Product,
    DeliveryDate,
    CASE 
        WHEN DeliveryDate < GETDATE() THEN 'Missed'
        WHEN DeliveryDate BETWEEN GETDATE() AND DATEADD(DAY, 7, GETDATE()) THEN 'Urgent'
        ELSE 'Upcoming'
    END AS DeliveryStatus,
    sum(OutCount) as OutCount
FROM VW_QueProOutDetail
GROUP BY PNum,
    Customer,
    Product,
    DeliveryDate,
    CASE 
        WHEN DeliveryDate < GETDATE() THEN 'Missed'
        WHEN DeliveryDate BETWEEN GETDATE() AND DATEADD(DAY, 7, GETDATE()) THEN 'Urgent'
        ELSE 'Upcoming'
    END
--ORDER BY DeliveryDate
;
GO

-- 1.1 What Has Been Shipped in the Past 30 Days
-- This query will find all records that have been shipped within the past 30 days.
-- Query for orders that have been shipped in the past 30 days with product and customer details
IF OBJECT_ID('auto_schedule.vw_ShippedPast30Days') IS NOT NULL
    DROP VIEW auto_schedule.vw_ShippedPast30Days;
GO
CREATE VIEW auto_schedule.vw_ShippedPast30Days AS
SELECT 
    s.PNum,
    s.OutDate AS ShippedDate,
    s.DeliveryDate,
    s.Customer,
    s.ProductID,
    s.Product,
	s.PartsName,
    COUNT(DISTINCT s.ProductID) AS ProductCount,
    SUM(s.OutCount) AS TotalShippedQty
FROM 
    VW_QueProOutDetail s
WHERE 
    s.OutDate BETWEEN DATEADD(DAY, -30, GETDATE()) AND GETDATE()
	and s.PNum is not null and s.PNum not in ('', ' ', '  ')
GROUP BY 
    s.PNum, s.OutDate, s.DeliveryDate, s.Customer, s.ProductID, s.Product, s.PartsName
--ORDER BY 
--    s.OutDate DESC, s.PNum, s.DeliveryDate, s.Customer, s.ProductID, s.Product, s.PartsName
;
GO

--1.2. Delivery Date in the Next 30 Days with PNum But Not Shipped (OutCount = 0)
-- Displays product and customer details for scheduled deliveries in the next 30 days that have PNum assigned but not shipped.
-- Query for deliveries in the next 30 days with PNum but not shipped, including product and customer
IF OBJECT_ID('auto_schedule.vw_PendingDeliveries') IS NOT NULL
    DROP VIEW auto_schedule.vw_PendingDeliveries;
GO
CREATE VIEW auto_schedule.vw_PendingDeliveries AS
SELECT 
    d.PNum,
    d.DeliveryDate,
    d.Customer,
    d.ProductID,
    d.Product, 
	s.PartsName,
    COUNT(DISTINCT d.ProductID) AS ProductCount,
    SUM(d.OrderCount) AS TotalOrderQty
FROM 
    VW_QueDGNBDetail d
LEFT JOIN 
    VW_QueProOutDetail s ON d.PNum = s.PNum
WHERE 
    d.DeliveryDate BETWEEN GETDATE() AND DATEADD(DAY, 30, GETDATE())
    and d.PNum is not null and d.PNum not in ('', ' ', '  ')
    AND (s.OutCount IS NULL OR s.OutCount = 0)
GROUP BY 
    d.PNum, d.DeliveryDate, d.Customer, d.ProductID, d.Product, s.PartsName
--ORDER BY 
--    d.DeliveryDate
;
GO

--1.3. Delivery Date in the Next 30 Days with a Scheduled Delivery Date But No PNum (Not Scheduled)
--Shows product and customer details for planned deliveries in the next 30 days that have not been scheduled (no PNum).
-- Query for deliveries in the next 30 days with a delivery date but no PNum (not scheduled), including product and customer
IF OBJECT_ID('auto_schedule.vw_UnscheduledDeliveries') IS NOT NULL
    DROP VIEW auto_schedule.vw_UnscheduledDeliveries;
GO
CREATE VIEW auto_schedule.vw_UnscheduledDeliveries AS
SELECT 
    d.DGNBilID,
    d.DeliveryDate,
    d.Customer,
    d.ProductID,
    d.Product,
    COUNT(DISTINCT d.ProductID) AS ProductCount,
    SUM(d.OrderCount) AS TotalOrderQty
FROM 
    VW_QueDGNBDetail d
LEFT JOIN 
    VW_QueProOutDetail s ON d.DGNBilID = s.DGNBilNum
WHERE 
    d.DeliveryDate BETWEEN GETDATE() AND DATEADD(DAY, 30, GETDATE())
    AND (s.PNum IS NULL OR s.PNum IN ('', ' ', '  '))
GROUP BY 
    d.DGNBilID, d.DeliveryDate, d.Customer, d.ProductID, d.Product
--ORDER BY 
--    d.DeliveryDate
;
GO

--2. Delivery Analysis with Shipping Status
-- Rank by delivery date, identify urgent orders, missed deliveries, and shipping status.
/*
SELECT 
    d.PNum,
    d.Customer,
    d.Product,
    d.DeliveryDate,
    a.State AS WorkOrderStatus,
	a.StatusDes,
    CASE 
        WHEN d.DeliveryDate < GETDATE() AND s.OutDate IS NULL THEN 'Missed & Not Shipped'
        WHEN d.DeliveryDate BETWEEN GETDATE() AND DATEADD(DAY, 7, GETDATE()) AND s.OutDate IS NULL THEN 'Urgent & Not Shipped'
        WHEN s.OutDate IS NOT NULL THEN 'Shipped'
        ELSE 'Upcoming & Not Shipped'
    END AS DeliveryStatus,
    SUM(d.PCount) AS TotalOrderQty,
    sum(d.OutCount) as OutCount,
    s.OutDate AS ShippedDate,
    sum(s.OutCount) AS ShippedQuantity
FROM VW_QueProOutDetail d
LEFT JOIN VW_QueProOutDetail s ON d.PNum = s.PNum
left join VW_QuePlanArrage a on a.PNum = s.PNum
group by d.PNum,
    d.Customer,
    d.Product,
    d.DeliveryDate,
    a.State,
	a.StatusDes,
    CASE 
        WHEN d.DeliveryDate < GETDATE() AND s.OutDate IS NULL THEN 'Missed & Not Shipped'
        WHEN d.DeliveryDate BETWEEN GETDATE() AND DATEADD(DAY, 7, GETDATE()) AND s.OutDate IS NULL THEN 'Urgent & Not Shipped'
        WHEN s.OutDate IS NOT NULL THEN 'Shipped'
        ELSE 'Upcoming & Not Shipped'
    END,
	s.OutDate
ORDER BY d.DeliveryDate;
*/
-- 3. Customer and Brand Analysis
-- Explore which customers and products have frequent orders, missed deadlines, and shipments.
-- Customer and brand analysis with missed and urgent orders
-- Query for deliveries in the next 30 days with a delivery date but no valid PNum (not scheduled), including product and customer
IF OBJECT_ID('auto_schedule.vw_CustomerAnalysis') IS NOT NULL
    DROP VIEW auto_schedule.vw_CustomerAnalysis;
GO
CREATE VIEW auto_schedule.vw_CustomerAnalysis AS
SELECT 
    d.DeliveryDate,
    d.Customer,
    d.ProductID,
    d.Product,
    COUNT(DISTINCT d.ProductID) AS ProductCount,
    SUM(d.OrderCount) AS TotalOrderQty
FROM 
    VW_QueDGNBDetail d
LEFT JOIN 
    VW_QueProOutDetail s ON d.DGNBilID = s.DGNBilNum
WHERE 
    d.DeliveryDate BETWEEN GETDATE() AND DATEADD(DAY, 30, GETDATE())
    AND (s.PNum IS NULL OR s.PNum IN ('', ' ', '  '))
GROUP BY 
    d.DeliveryDate, d.Customer, d.ProductID, d.Product
--ORDER BY 
--    d.DeliveryDate
;
GO

--4. Work Order Status and Shipping Analysis
-- Analyze the current work order status and whether the products are shipped.
-- Analysis of work order status and shipping status
IF OBJECT_ID('auto_schedule.vw_WorkOrderStatus') IS NOT NULL
    DROP VIEW auto_schedule.vw_WorkOrderStatus;
GO
CREATE VIEW auto_schedule.vw_WorkOrderStatus AS
SELECT 
    p.StatusDes AS WorkOrderStatus,
    COUNT(*) AS WorkOrderCount,
    SUM(CASE WHEN s.OutDate IS NOT NULL THEN 1 ELSE 0 END) AS ShippedCount,
    SUM(CASE WHEN s.OutDate IS NULL THEN 1 ELSE 0 END) AS NotShippedCount
FROM VW_QuePlanArrage p
LEFT JOIN VW_QueProOutDetail s ON p.PNum = s.PNum
GROUP BY p.StatusDes
--ORDER BY COUNT(*) DESC
;
GO

-- 5. Late Orders Impact Analysis
--Identify which customers and products have been most affected by late deliveries.
-- Impact of late deliveries on customers and products, grouped by month for the past year
IF OBJECT_ID('auto_schedule.vw_LateOrdersImpact') IS NOT NULL
    DROP VIEW auto_schedule.vw_LateOrdersImpact;
GO
CREATE VIEW auto_schedule.vw_LateOrdersImpact AS
SELECT 
    d.Customer,
    d.Product,
    DATEPART(YEAR, d.DeliveryDate) AS DeliveryYear,
    DATEPART(MONTH, d.DeliveryDate) AS DeliveryMonth,
    COUNT(*) AS TotalOrders,
    SUM(CASE WHEN d.DeliveryDate < GETDATE() AND (s.OutDate IS NULL OR s.OutDate > d.DeliveryDate) THEN 1 ELSE 0 END) AS LateOrders,
    SUM(CAST(d.OrderCount AS BIGINT)) AS TotalOrderQty,
    SUM(CASE WHEN d.DeliveryDate < GETDATE() AND (s.OutDate IS NULL OR s.OutDate > d.DeliveryDate) THEN CAST(d.OrderCount AS BIGINT) ELSE 0 END) AS LateOrderQty
FROM 
    VW_QueDGNBDetail d
LEFT JOIN 
    VW_QueProOutDetail s ON d.PNum = s.PNum
WHERE 
    d.DeliveryDate BETWEEN DATEADD(YEAR, -1, GETDATE()) AND GETDATE()
GROUP BY 
    d.Customer, 
    d.Product, 
    DATEPART(YEAR, d.DeliveryDate), 
    DATEPART(MONTH, d.DeliveryDate)
--ORDER BY 
--    DeliveryYear DESC, 
--    DeliveryMonth DESC, 
--    LateOrders DESC
;
GO

-- 6. Machine/Device Utilization Analysis
--Check which machines are handling most work orders and if any delays are associated with them.
-- Machine utilization and associated delays, with BIGINT conversion
IF OBJECT_ID('auto_schedule.vw_MachineUtilization') IS NOT NULL
    DROP VIEW auto_schedule.vw_MachineUtilization;
GO
CREATE VIEW auto_schedule.vw_MachineUtilization AS
SELECT 
	p.JSName as Process,
    p.DevName AS DeviceName,
    COUNT(*) AS UsageCount,
    AVG(CAST(p.FTime AS BIGINT)) AS AvgTimeSpent,
    SUM(CASE WHEN p.StatusDes = 'Producing' AND d.DeliveryDate < GETDATE() THEN 1 ELSE 0 END) AS DelayedCount,
    SUM(CASE WHEN p.StatusDes = '已完成' OR p.StatusDes = 'Completed' THEN 1 ELSE 0 END) AS CompletedCount,
    SUM(CASE WHEN p.StatusDes = 'Pause' THEN 1 ELSE 0 END) AS PausedCount,
    SUM(CASE WHEN p.StatusDes = 'Waitting' THEN 1 ELSE 0 END) AS WaitingCount
FROM 
    VW_QuePlanArrage p
LEFT JOIN 
    VW_QueDGNBDetail d ON p.PNum = d.PNum
WHERE 
    d.DeliveryDate BETWEEN DATEADD(YEAR, -1, GETDATE()) AND GETDATE()
GROUP BY 
    p.JSName, p.DevName
--ORDER BY 
--    UsageCount DESC
;
GO

-- 7. Priority and Urgency Analysis
-- Assign a priority score based on delivery urgency, work order status, and shipping status.
-- Priority score based on delivery, work order, and shipping status
-- and urgency analysis with handling for missing PNum and potential duplicates
IF OBJECT_ID('auto_schedule.vw_PriorityUrgency') IS NOT NULL
    DROP VIEW auto_schedule.vw_PriorityUrgency;
GO
CREATE VIEW auto_schedule.vw_PriorityUrgency AS
WITH AggregatedOrders AS (
    SELECT 
        COALESCE(p.PNum, 'Unassigned') AS PNum,  -- Treat missing PNum as 'Unassigned'
        p.Customer,
        p.ProductID,
        p.ProductName AS Product,
        p.PEndTime AS DeliveryDate,
        COUNT(DISTINCT p.ProductID) AS ProductCount,  -- Count of distinct products for each PNum
        SUM(CAST(p.PCount AS BIGINT)) AS TotalOrderQty,  -- Aggregate planned production quantity
        MAX(p.StatusDes) AS WorkOrderStatus,  -- Most relevant status for work order
        MAX(s.OutDate) AS ShippedDate  -- Latest shipping date, if any
    FROM 
        VW_QuePlanArrage p
    LEFT JOIN 
        VW_QueProOutDetail s ON p.PNum = s.PNum
    WHERE 
        p.PEndTime BETWEEN DATEADD(YEAR, -1, GETDATE()) AND GETDATE()  -- Filter for past year
    GROUP BY 
        COALESCE(p.PNum, 'Unassigned'), p.Customer, p.ProductID, p.ProductName, p.PEndTime
)

-- Calculate Priority and Urgency based on the Aggregated Data
SELECT 
    a.PNum,
    a.Customer,
    a.Product,
    a.DeliveryDate,
    a.ProductCount,
    a.TotalOrderQty,
    a.WorkOrderStatus,
    a.ShippedDate,
    CASE 
        WHEN a.DeliveryDate < GETDATE() AND (a.ShippedDate IS NULL OR a.ShippedDate > a.DeliveryDate) THEN 100  -- Missed delivery and not shipped
        WHEN a.DeliveryDate BETWEEN GETDATE() AND DATEADD(DAY, 7, GETDATE()) AND (a.ShippedDate IS NULL OR a.ShippedDate > a.DeliveryDate) THEN 80  -- Urgent and not shipped
        WHEN a.WorkOrderStatus = 'Producing' THEN 60  -- In progress
        WHEN a.WorkOrderStatus IN ('Waitting', 'Pause') THEN 40  -- Waiting or Paused
        ELSE 20  -- Lower priority
    END AS PriorityScore
FROM 
    AggregatedOrders a
	where a.WorkOrderStatus not in ('Completed', '已完成')
--ORDER BY 
--    PriorityScore DESC, a.DeliveryDate
;
GO






