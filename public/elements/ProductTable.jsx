/**
 * ProductTable - Custom React element for compact product comparison display.
 *
 * Features:
 * - Fixed table layout with no horizontal scroll
 * - 10px font with tight padding for compact display
 * - Sticky first column for product names
 * - Product names are clickable links to official URLs
 * - Manufacturer shown as subtitle under product name
 * - Status indicators for pending/failed cells
 * - CSS ellipsis truncation with hover tooltips
 * - Dark/light mode support via CSS variables
 * - Footer showing "Showing X of Y products"
 *
 * NOTE: Props are globally injected by Chainlit, not passed as function arguments.
 */

export default function ProductTable() {
  // Props are globally injected by Chainlit
  const {
    products = [],
    fields = [],
    fieldLabels = {},
    fieldTypes = {},
    totalProducts = 0,
    productType = "products",
  } = props;

  // Calculate column widths based on field types
  const PRODUCT_COL_WIDTH = 28; // Product column takes 28%
  const REMAINING_WIDTH = 72; // Remaining 72% for data columns

  const getColumnWidths = () => {
    if (fields.length === 0) return [];

    // Count narrow vs standard fields
    const narrowCount = fields.filter((f) => fieldTypes[f] === "narrow").length;
    const standardCount = fields.length - narrowCount;

    // Narrow fields get 14%, standard fields share the rest
    const narrowWidth = 14;
    const usedByNarrow = narrowCount * narrowWidth;
    const remainingForStandard = REMAINING_WIDTH - usedByNarrow;
    const standardWidth =
      standardCount > 0 ? remainingForStandard / standardCount : 0;

    return fields.map((field) =>
      fieldTypes[field] === "narrow" ? narrowWidth : standardWidth
    );
  };

  const columnWidths = getColumnWidths();

  // Inline styles for theme-aware compact table
  const styles = {
    container: {
      width: "100%",
      overflowX: "hidden",
      marginTop: "0.75rem",
      marginBottom: "0.5rem",
      borderRadius: "6px",
      border: "1px solid var(--shortlist-dark-border, #2a2725)",
    },
    table: {
      width: "100%",
      borderCollapse: "collapse",
      tableLayout: "fixed",
      fontSize: "10px",
      lineHeight: "1.4",
    },
    th: {
      padding: "5px 6px",
      textAlign: "left",
      fontWeight: 600,
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap",
      backgroundColor: "var(--shortlist-dark-card, #1e1c1a)",
      borderBottom: "2px solid var(--shortlist-primary, #d97757)",
      color: "var(--shortlist-dark-text, #d1cbc3)",
    },
    thProduct: {
      padding: "5px 6px",
      textAlign: "left",
      fontWeight: 600,
      backgroundColor: "var(--shortlist-dark-card, #1e1c1a)",
      borderBottom: "2px solid var(--shortlist-primary, #d97757)",
      color: "var(--shortlist-dark-text, #d1cbc3)",
      position: "sticky",
      left: 0,
      zIndex: 2,
    },
    td: {
      padding: "5px 6px",
      borderBottom: "1px solid var(--shortlist-dark-border, #2a2725)",
      color: "var(--shortlist-dark-text, #d1cbc3)",
      verticalAlign: "top",
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap",
      maxWidth: 0,
    },
    tdProduct: {
      padding: "5px 6px",
      borderBottom: "1px solid var(--shortlist-dark-border, #2a2725)",
      backgroundColor: "var(--shortlist-dark-bg, #151311)",
      position: "sticky",
      left: 0,
      zIndex: 1,
      overflow: "hidden",
      maxWidth: 0,
    },
    productLink: {
      color: "var(--shortlist-primary, #d97757)",
      textDecoration: "none",
      fontWeight: 500,
      display: "block",
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap",
    },
    manufacturer: {
      fontSize: "9px",
      color: "var(--shortlist-dark-muted, #7a746c)",
      marginTop: "1px",
      overflow: "hidden",
      textOverflow: "ellipsis",
      whiteSpace: "nowrap",
    },
    pending: {
      color: "var(--shortlist-gold, #cfa245)",
      fontStyle: "italic",
      fontSize: "9px",
    },
    failed: {
      color: "#e25555",
      fontStyle: "italic",
      fontSize: "9px",
    },
    empty: {
      color: "var(--shortlist-dark-muted, #7a746c)",
    },
    footer: {
      padding: "5px 6px",
      fontSize: "9px",
      color: "var(--shortlist-dark-muted, #7a746c)",
      textAlign: "right",
      borderTop: "1px solid var(--shortlist-dark-border, #2a2725)",
      backgroundColor: "var(--shortlist-dark-card, #1e1c1a)",
    },
  };

  // Render cell value with status indicators and tooltip
  const renderCell = (cell) => {
    if (!cell) {
      return <span style={styles.empty}>—</span>;
    }

    const { value, status } = cell;

    if (status === "pending") {
      return <span style={styles.pending}>pending...</span>;
    }

    if (status === "failed") {
      return <span style={styles.failed}>unavailable</span>;
    }

    if (value === null || value === undefined || value === "") {
      return <span style={styles.empty}>—</span>;
    }

    const displayValue = String(value);
    return <span title={displayValue}>{displayValue}</span>;
  };

  // Render product name cell with link and manufacturer
  const renderProductCell = (product) => {
    const nameContent = product.url ? (
      <a
        href={product.url}
        target="_blank"
        rel="noopener noreferrer"
        style={styles.productLink}
        title={product.name}
      >
        {product.name}
      </a>
    ) : (
      <span
        style={{ ...styles.productLink, color: "inherit" }}
        title={product.name}
      >
        {product.name}
      </span>
    );

    return (
      <div>
        {nameContent}
        {product.manufacturer && (
          <div style={styles.manufacturer} title={product.manufacturer}>
            {product.manufacturer}
          </div>
        )}
      </div>
    );
  };

  if (!products.length) {
    return (
      <div style={{ padding: "1rem", color: "var(--shortlist-dark-muted)" }}>
        No products to display.
      </div>
    );
  }

  const showingCount = products.length;
  const hasMore = totalProducts > showingCount;

  return (
    <div className="product-table-container" style={styles.container}>
      <table style={styles.table}>
        <colgroup>
          <col style={{ width: `${PRODUCT_COL_WIDTH}%` }} />
          {columnWidths.map((width, i) => (
            <col key={i} style={{ width: `${width}%` }} />
          ))}
        </colgroup>
        <thead>
          <tr>
            <th style={styles.thProduct}>Product</th>
            {fields.map((field) => (
              <th key={field} style={styles.th} title={fieldLabels[field] || field}>
                {fieldLabels[field] || field}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {products.map((product, index) => (
            <tr key={product.id || index} className="product-table-row">
              <td style={styles.tdProduct}>{renderProductCell(product)}</td>
              {fields.map((field) => (
                <td key={field} style={styles.td}>
                  {renderCell(product.cells?.[field])}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
      <div style={styles.footer}>
        {hasMore
          ? `Showing ${showingCount} of ${totalProducts} ${productType}`
          : `${showingCount} ${productType}`}
        {hasMore && " • Export CSV for full list"}
      </div>
    </div>
  );
}
